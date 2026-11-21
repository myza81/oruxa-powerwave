"""Static regression checks confirming that the Source Default modal
(#perUnitProfilesOverlay) and all its associated functions were removed
in PU-UI-001 Step B.

The original classes in this file tested arithmetic correctness inside
the SD modal's current-base preview and voltage-reference block.  Those
functions no longer exist; these replacement tests guard the removal
contract instead -- the functions must stay gone, and the surviving
navigation/display surfaces must remain intact.

Same source-text substring-assertion pattern every other
`test_frontend_*.py` file in this suite already uses.
"""

from __future__ import annotations

from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


class TestSourceDefaultModalRemovedInPuUi001:
    """PU-UI-001 Step B: the Source Default modal and all its markup
    have been removed.  PU configuration is managed via Recording
    Details."""

    def test_sd_overlay_markup_is_gone(self):
        source = _source()
        assert 'id="perUnitProfilesOverlay"' not in source
        assert 'id="perUnitSourceSelect"' not in source
        assert 'id="perUnitProfileFields"' not in source

    def test_sd_link_in_recording_info_is_gone(self):
        source = _source()
        assert 'ww-rd-pu-source-default-link' not in source
        assert 'Configure Source Default' not in source


class TestSourceDefaultFunctionsRemovedInPuUi001:
    """PU-UI-001 Step B: all SD-modal-only JS functions are gone."""

    def test_open_close_functions_removed(self):
        source = _source()
        assert 'async function wwOpenPerUnitProfilesModal' not in source
        assert 'function wwClosePerUnitProfilesModal()' not in source

    def test_editor_state_functions_removed(self):
        source = _source()
        assert 'function wwPerUnitConfigToEditorState(' not in source
        assert 'function wwPerUnitEditorResolvedCurrentBaseText(' not in source
        assert 'function wwPerUnitDerivedCurrentBaseKa(' not in source

    def test_render_functions_removed(self):
        source = _source()
        assert 'function wwRenderVoltageReferenceBlock(' not in source
        assert 'function wwRenderPerUnitProfileEditor(' not in source
        assert 'function wwRenderPerUnitSourceSelect(' not in source
        assert 'function wwRenderPerUnitSourceStatusLine(' not in source

    def test_apply_delete_functions_removed(self):
        source = _source()
        assert 'async function wwApplyPerUnitProfileEditor()' not in source
        assert 'async function wwDeletePerUnitProfileEditor()' not in source

    def test_wire_events_function_removed(self):
        source = _source()
        assert 'function wwWirePerUnitProfileFieldsEvents()' not in source

    def test_fetch_source_configs_function_removed(self):
        source = _source()
        assert 'function wwFetchPerUnitSourceConfigs' not in source

    def test_per_unit_source_configs_state_removed(self):
        source = _source()
        assert 'perUnitSourceConfigs: new Map()' not in source

    def test_per_unit_constants_removed(self):
        """PER_UNIT_SQRT_3 / _LINE_TO_GROUND / _LINE_TO_LINE were only
        referenced by SD modal and MG overlay functions; both removed."""
        source = _source()
        assert 'const PER_UNIT_SQRT_3' not in source
        assert 'const PER_UNIT_LINE_TO_GROUND' not in source
        assert 'const PER_UNIT_LINE_TO_LINE' not in source

    def test_sd_api_path_references_removed(self):
        """The SD modal was the only frontend caller of the per-unit/sources
        endpoints; removing it means those path strings are gone too."""
        source = _source()
        assert '"/per-unit/sources"' not in source
        assert '"/per-unit/sources/"' not in source


class TestSlice1Through3NavigationUnaffected:
    """PU-UI-001 Step B is a navigation/surface removal only -- the
    underlying waveform display, unit mode toggle, and per-unit details
    popover remain completely intact."""

    def test_per_unit_settings_hub_retired_rd_is_the_config_entry_point(self):
        source = _source()
        assert 'id="wwOpenPerUnitSettingsBtn"' not in source

    def test_coverage_hub_section_retired_banner_is_the_new_signal(self):
        source = _source()
        assert 'id="wwPuCoverageBody"' not in source
        assert 'id="wwPuConfigBanner"' in source

    def test_per_unit_details_popover_still_present(self):
        source = _source()
        assert 'id="wwChannelMenuPerUnitBtn"' in source
        assert 'id="wwChannelPerUnitOverlay"' in source

    def test_navigate_to_rd_helper_replaces_modal_entry_points(self):
        source = _source()
        assert 'function wwNavigateToRdForPuConfiguration(' in source
        assert 'function wwNavigateToRdForGroup(' in source
