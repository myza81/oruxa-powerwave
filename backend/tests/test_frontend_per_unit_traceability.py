"""Static regression checks for Slice 3 of the Per-Unit Settings
hierarchy (frontend/index.html) -- channel-level Per-Unit traceability,
reached via a third item ("Per-Unit Details...") on the existing
RECORDINGS-sidebar channel context menu (`#wwChannelContextMenu`,
established by DEC-070's Rename/Change colour customization).

Same source-text substring-assertion pattern every other
`test_frontend_*.py` file in this suite already uses. Backend
classification/provenance semantics (DEC-051/DEC-052 agreement,
LL/LG effective base, truthful Source Default display) have their own
focused coverage in `test_per_unit_provenance_service.py`/
`test_per_unit_provenance_api.py` -- this file only checks the frontend
surface renders/wires correctly.
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


class TestTraceabilityAffordanceAppearsWhereIntended:
    """Checklist item 1: reuses the existing channel context menu,
    doesn't invent a new interaction surface."""

    def test_context_menu_gains_a_third_item(self):
        source = _source()
        menu_body = _function_body(source, 'id="wwChannelContextMenu"', "</div>")
        assert 'id="wwChannelMenuRenameBtn"' in menu_body
        assert 'id="wwChannelMenuColorBtn"' in menu_body
        assert 'id="wwChannelMenuPerUnitBtn"' in menu_body
        assert "Per-Unit Details" in menu_body

    def test_menu_item_opens_the_popover(self):
        source = _source()
        wiring = _function_body(source, 'document.getElementById("wwChannelMenuPerUnitBtn")', "});")
        assert "wwOpenChannelPerUnitModal()" in wiring

    def test_popover_reuses_the_existing_confirm_overlay_shell(self):
        source = _source()
        assert 'class="confirm-overlay" id="wwChannelPerUnitOverlay"' in source

    def test_popover_reuses_the_calculated_channels_info_strip_pattern(self):
        """No new visual system -- the same label/value strip the
        Calculated Channels page's own selected-channel preview already
        established."""
        source = _source()
        body = _function_body(source, 'id="wwChannelPerUnitOverlay"', "<!--")
        assert 'class="ww-cc-preview-info-strip"' in body


class TestMeasurementGroupNameShownCorrectly:
    """Checklist item 2."""

    def test_render_function_labels_measurement_group_source(self):
        source = _source()
        body = _function_body(
            source, "function wwRenderChannelPerUnitResolution(resolution)", "async function wwFetchChannelPerUnitResolution"
        )
        assert '"Measurement Group: "' in body
        assert "resolution.measurement_group_name" in body

    def test_nominal_and_channel_interpretation_rows_present_for_a_voltage_group(self):
        source = _source()
        body = _function_body(
            source, "function wwRenderChannelPerUnitResolution(resolution)", "async function wwFetchChannelPerUnitResolution"
        )
        assert '"Nominal voltage"' in body
        assert '"Channel interpretation"' in body
        assert '"Effective base"' in body

    def test_equipment_rating_row_present_for_a_current_group(self):
        source = _source()
        body = _function_body(
            source, "function wwRenderChannelPerUnitResolution(resolution)", "async function wwFetchChannelPerUnitResolution"
        )
        assert '"Equipment rating"' in body
        assert "resolution.applicable_voltage_ll_kv" in body


class TestSourceDefaultShownCorrectly:
    """Checklist items 3, 5: Source Default label present, and no
    fabricated LL/LG suffix is ever attached to its own base value."""

    def test_source_default_label_present(self):
        source = _source()
        body = _function_body(
            source, "function wwRenderChannelPerUnitResolution(resolution)", "async function wwFetchChannelPerUnitResolution"
        )
        assert '"Source Default"' in body

    def test_source_default_current_row_never_appends_a_reference_suffix(self):
        """Follow-up enhancement update: Source Default VOLTAGE now
        legitimately shares the same "Effective base" + reference-suffix
        presentation as Measurement Groups (see
        TestNominalAndInterpretationForSourceDefaultVoltage below) --
        but Source Default CURRENT (no nominal_base_kv, no reference-
        aware adjustment in its own arithmetic) must still never get a
        suffix, in its own dedicated branch."""
        source = _source()
        body = _function_body(
            source,
            "// Source Default Current: deliberately plain",
            "rows.push(wwPerUnitInfoRowHtml(\"Status\"",
        )
        assert "+ suffix" not in body
        assert "refAbbrev" not in body


class TestEffectiveBaseShownForGroupAwareLGVoltage:
    """Checklist item 4."""

    def test_lg_reference_maps_to_the_correct_abbreviation(self):
        source = _source()
        body = _function_body(source, "function wwPerUnitReferenceAbbrev(reference)", "}")
        assert '"line_to_ground"' in body
        assert '"L-G"' in body
        assert '"line_to_line"' in body
        assert '"L-L"' in body


class TestNeedsConfigurationStateShownClearly:
    """Checklist item 6."""

    def test_status_and_reason_rows_present(self):
        source = _source()
        body = _function_body(
            source, "function wwRenderChannelPerUnitResolution(resolution)", "async function wwFetchChannelPerUnitResolution"
        )
        assert '"Needs configuration"' in body
        assert "resolution.reason" in body


class TestNotApplicableStateDoesNotShowBogusBase:
    """Checklist item 7."""

    def test_not_applicable_short_circuits_before_any_base_row_is_built(self):
        source = _source()
        body = _function_body(
            source, "function wwRenderChannelPerUnitResolution(resolution)", "async function wwFetchChannelPerUnitResolution"
        )
        na_branch_index = body.index('resolution.status === "not_applicable"')
        return_index = body.index("return;", na_branch_index)
        first_row_build_index = body.index("wwPerUnitInfoRowHtml(", na_branch_index)
        assert return_index < first_row_build_index

    def test_not_applicable_message_is_the_fixed_neutral_copy(self):
        source = _source()
        assert "Per-unit conversion is not applicable to this channel." in source


class TestSlice1And2NavigationRemainsIntact:
    """Checklist items 8, 9: Slice 1's Per-Unit Settings hierarchy and
    Slice 2's coverage section are unaffected by this addition."""

    def test_per_unit_settings_entry_point_still_present(self):
        source = _source()
        assert 'id="wwOpenPerUnitSettingsBtn"' in source

    def test_coverage_section_still_present(self):
        source = _source()
        assert 'id="wwPuCoverageSection"' in source
        assert 'id="wwPuCoverageBody"' in source


class TestUnitModeSwitchingUnchanged:
    """Checklist item 10: Per Unit / Engineering Units display-mode
    switching is untouched by this slice, and still never opens any
    configuration/traceability surface as a side effect."""

    def test_per_unit_selection_still_only_calls_apply_unit_mode(self):
        source = _source()
        wiring = _function_body(
            source,
            'document.querySelector(\'#wwUnitModeMenu .ww-split-menu-item[data-unit-mode="per_unit"]\')',
            'document.getElementById("wwOpenPerUnitSettingsBtn")',
        )
        assert 'await wwApplyUnitMode("per_unit");' in wiring
        assert "wwOpenChannelPerUnitModal" not in wiring


class TestReadOnlyNeverMutates:
    """The popover must only ever GET -- opening it can never change
    per-unit configuration, group membership, or anything else."""

    def test_popover_open_and_fetch_functions_never_mutate(self):
        source = _source()
        body = _function_body(
            source, "async function wwFetchChannelPerUnitResolution(sourceId, channelName)", "async function wwOpenChannelPerUnitModal()"
        )
        for verb in ('"POST"', '"PUT"', '"PATCH"', '"DELETE"', "method:"):
            assert verb not in body

    def test_new_endpoint_path_is_additive(self):
        source = _source()
        assert "/per-unit-resolution" in source
