"""Static regression checks for Slice 2 of the Per-Unit Settings
hierarchy (frontend/index.html) -- the "Per-unit coverage" section added
to the Slice 1 parent surface (`#perUnitSettingsOverlay`), backed by the
new additive `GET .../per-unit/sources/{source_id}/coverage` endpoint.

Same source-text substring-assertion pattern every other
`test_frontend_*.py` file in this suite already uses. Backend
classification semantics (mutually-exclusive counts, DEC-051 precedence,
Angle/digital exclusion) have their own focused coverage in
`test_per_unit_coverage_service.py`/`test_per_unit_coverage_api.py` --
this file only checks the frontend surface renders/labels/wires
correctly.
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


class TestCoverageSectionExists:
    """Checklist item 1: the coverage section appears in Per-Unit
    Settings."""

    def test_coverage_section_markup_exists_inside_the_parent_surface(self):
        source = _source()
        body = _function_body(source, 'id="perUnitSettingsOverlay"', '<!-- Phase 5C (DEC-049): "Manage Per-Unit Bases"')
        assert 'id="wwPuCoverageSection"' in body
        assert 'id="wwPuCoverageBody"' in body
        assert "Per-unit coverage" in body


class TestCoverageLabels:
    """Checklist item 2: correct labels, sourced from the rendering
    function itself (not just static markup)."""

    def test_render_function_uses_the_required_three_labels(self):
        source = _source()
        body = _function_body(
            source, "async function wwLoadAndRenderPerUnitCoverage()", "// ------"
        )
        assert '"Measurement Groups"' in body
        assert '"Source Default"' in body
        assert '"Needs configuration"' in body


class TestSelectedRecordingContextIsClear:
    """Checklist item 3: coverage clearly corresponds to one selected
    recording/source -- the parent surface reuses the same "Recording"
    selector shape the two child modals already use, and switching it
    re-fetches coverage for the newly selected source only."""

    def test_recording_selector_exists_in_the_parent_surface(self):
        source = _source()
        body = _function_body(source, 'id="perUnitSettingsOverlay"', '<!-- Phase 5C (DEC-049): "Manage Per-Unit Bases"')
        assert 'id="perUnitSettingsSourceSelect"' in body
        assert "Recording" in body

    def test_selecting_a_different_recording_reloads_coverage_for_it(self):
        source = _source()
        wiring = _function_body(source, 'document.getElementById("perUnitSettingsSourceSelect").addEventListener', "});")
        assert "wwPerUnitSettingsSourceSelectChange" in wiring
        body = _function_body(
            source, "async function wwPerUnitSettingsSourceSelectChange(sourceId)", "        function wwPuCoverageRowHtml"
        )
        assert "wwPuSettingsSelectedSourceId = sourceId;" in body
        assert "wwLoadAndRenderPerUnitCoverage();" in body

    def test_coverage_fetch_is_scoped_to_the_selected_source_id(self):
        source = _source()
        body = _function_body(
            source, "async function wwFetchPerUnitCoverage(sourceId)", "async function wwLoadAndRenderPerUnitCoverage()"
        )
        assert "encodeURIComponent(sourceId)" in body
        assert "/per-unit/sources/" in body
        assert "/coverage" in body


class TestEmptyAndZeroStates:
    """Checklist item 4: no recordings, no applicable channels, and a
    fetch failure are each an explicit, distinct, neutral message --
    never a misleading zero-count warning."""

    def test_no_recordings_loaded_state(self):
        source = _source()
        body = _function_body(source, "async function wwLoadAndRenderPerUnitCoverage()", "return;")
        assert "Upload a recording to see Per-Unit coverage." in body

    def test_no_applicable_channels_state_is_neutral_not_a_warning(self):
        source = _source()
        body = _function_body(source, "async function wwLoadAndRenderPerUnitCoverage()", "// ------")
        assert "No applicable Voltage/Current channels for per-unit conversion." in body
        # The neutral empty-state message itself must never be wrapped in
        # the error/attention styling used for an actual fetch failure.
        neutral_line_index = body.index("No applicable Voltage/Current channels")
        preceding = body[max(0, neutral_line_index - 40) : neutral_line_index]
        assert '"hint error"' not in preceding

    def test_fetch_failure_state_is_distinct_from_the_empty_state(self):
        source = _source()
        body = _function_body(source, "async function wwLoadAndRenderPerUnitCoverage()", "// ------")
        assert "Failed to load coverage" in body
        assert '"hint error"' in body


class TestWarningTreatmentOnlyWhenNeedsConfigurationPositive:
    """Checklist item 5: only the Needs configuration row may carry
    attention styling, and only when its own count is > 0."""

    def test_attention_class_is_conditional_on_needs_configuration_count(self):
        source = _source()
        body = _function_body(
            source, "async function wwLoadAndRenderPerUnitCoverage()", "// ------"
        )
        assert "coverage.needs_configuration_count > 0" in body
        assert "needsAttention" in body

    def test_measurement_groups_and_source_default_rows_never_get_attention_styling(self):
        source = _source()
        body = _function_body(
            source, "async function wwLoadAndRenderPerUnitCoverage()", "// ------"
        )
        assert 'wwPuCoverageRowHtml("Measurement Groups", coverage.measurement_group_count, false)' in body
        assert 'wwPuCoverageRowHtml("Source Default", coverage.source_default_count, false)' in body
        assert 'wwPuCoverageRowHtml("Needs configuration", coverage.needs_configuration_count, needsAttention)' in body

    def test_attention_styling_never_uses_error_red(self):
        source = _source()
        rule = _function_body(source, ".ww-pu-coverage-row--attention", "}")
        assert "var(--error)" not in rule
        assert "var(--warn)" in rule


class TestSourceDefaultUsageIsNotAnError:
    """Checklist item 6: valid Source Default usage must never be shown
    as an error -- neither its own badge/chip (Slice 1) nor its coverage
    count row (Slice 2) ever uses error/red styling."""

    def test_source_default_coverage_row_uses_the_same_neutral_row_class_as_measurement_groups(self):
        source = _source()
        rule = _function_body(source, ".ww-pu-coverage-row {", "}")
        assert "var(--error)" not in rule

    def test_source_default_badge_still_never_uses_warning_or_error_styling(self):
        source = _source()
        rule = _function_body(source, ".ww-mg-badge--fallback {", "}")
        assert "var(--warn)" not in rule
        assert "var(--error)" not in rule


class TestSlice1NavigationRemainsIntact:
    """Checklist item 7: Slice 1's own navigation (single toolbar entry,
    routing into both child modals, back-links) is unaffected by adding
    coverage."""

    def test_single_toolbar_entry_point_still_present(self):
        source = _source()
        assert 'id="wwOpenPerUnitSettingsBtn"' in source

    def test_both_child_modals_still_reachable_from_the_parent(self):
        source = _source()
        wiring_mg = _function_body(source, 'document.getElementById("wwOpenMeasurementGroupsFromSettingsBtn").addEventListener', "});")
        assert "wwOpenMeasurementGroupsModal()" in wiring_mg
        wiring_sd = _function_body(source, 'document.getElementById("wwOpenPerUnitProfilesFromSettingsBtn").addEventListener', "});")
        assert "wwOpenPerUnitProfilesModal()" in wiring_sd

    def test_back_links_still_present_and_wired(self):
        source = _source()
        assert 'id="wwPerUnitProfilesBackToSettingsBtn"' in source
        assert 'id="wwMeasurementGroupsBackToSettingsBtn"' in source

    def test_per_unit_display_mode_selection_still_never_opens_any_surface(self):
        source = _source()
        wiring = _function_body(
            source,
            'document.querySelector(\'#wwUnitModeMenu .ww-split-menu-item[data-unit-mode="per_unit"]\')',
            'document.getElementById("wwOpenPerUnitSettingsBtn")',
        )
        assert "wwOpenPerUnitSettingsModal" not in wiring
        assert "wwOpenPerUnitProfilesModal" not in wiring
        assert "wwOpenMeasurementGroupsModal" not in wiring
