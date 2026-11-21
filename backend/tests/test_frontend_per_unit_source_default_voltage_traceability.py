"""Static regression checks for the Slice 4 follow-up enhancement:
Source Default Voltage now shows the same three engineering concepts a
Measurement Group already shows -- Nominal voltage / Channel
interpretation / Effective base -- in both the Per-Unit Details popover
(Slice 3) and the Source Default editor's own preview.

Same source-text substring-assertion pattern every other
`test_frontend_*.py` file in this suite already uses. Backend
provenance semantics have their own focused coverage in
`test_per_unit_provenance_service.py`/`test_per_unit_provenance_api.py`
-- this file only checks the frontend surfaces render/label correctly.
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


class TestPopoverSharesTheThreeConceptPresentation:
    """Checklist item: the Per-Unit Details popover now builds Nominal
    voltage/Channel interpretation/Effective base generically off
    `resolution.nominal_base_kv`, not gated to Measurement Groups only,
    so Source Default Voltage (which now also reports that field) gets
    the identical presentation."""

    def test_nominal_and_interpretation_rows_are_not_gated_to_measurement_group(self):
        source = _source()
        body = _function_body(
            source, "function wwRenderChannelPerUnitResolution(resolution)", "async function wwFetchChannelPerUnitResolution"
        )
        # The nominal_base_kv check must NOT be nested inside a
        # `source_kind === "measurement_group"` branch -- it must be a
        # sibling, scope-independent check.
        nominal_check_index = body.index("resolution.nominal_base_kv != null")
        preceding = body[:nominal_check_index]
        # The immediately-preceding structural block is the Source-line
        # if/else-if (which closes before the nominal check begins) --
        # confirm the nominal check is not textually nested one level
        # deeper inside that block by checking indentation is shallow
        # (12 spaces, matching the other top-level statements in this
        # function) rather than 16+ (nested one level inside the
        # Source-line if-block).
        line_start = preceding.rfind("\n") + 1
        indent = len(body[line_start:nominal_check_index]) - len(body[line_start:nominal_check_index].lstrip())
        assert indent <= 12

    def test_effective_base_dispatches_on_nominal_presence_not_source_kind_alone(self):
        source = _source()
        body = _function_body(
            source, "function wwRenderChannelPerUnitResolution(resolution)", "async function wwFetchChannelPerUnitResolution"
        )
        assert "if (resolution.nominal_base_kv != null) {" in body
        # The Voltage (either-scope) "Effective base" branch, keyed on
        # nominal_base_kv presence -- appears before the Measurement-
        # Group-only and Source-Default-Current-only fallback branches.
        voltage_branch_index = body.index("if (resolution.nominal_base_kv != null) {", body.index("effective_base_amount != null"))
        mg_only_index = body.index('resolution.source_kind === "measurement_group"', voltage_branch_index)
        sd_only_index = body.index('resolution.source_kind === "source_default"', mg_only_index)
        assert voltage_branch_index < mg_only_index < sd_only_index


class TestSourceDefaultCurrentNeverGetsNominalFields:
    """Checklist item 4 (frontend side): Source Default Current keeps
    its own plain, un-annotated label -- no Nominal voltage/Channel
    interpretation row ever renders for it, since the backend never
    populates nominal_base_kv for Current."""

    def test_source_default_current_fallback_label_is_engineering_type_aware(self):
        source = _source()
        body = _function_body(
            source, "// Source Default Current: deliberately plain", 'rows.push(wwPerUnitInfoRowHtml("Status"'
        )
        assert 'resolution.engineering_type === "Voltage" ? "Voltage base" : "Current base"' in body
        assert "Channel interpretation" not in body
        assert "Nominal voltage" not in body


class TestEditorPreviewFunctionsRemovedInPuUi001:
    """PU-UI-001 Step B: the SD modal's voltage-reference preview helpers
    (`wwPerUnitEffectiveVoltageBaseLines`, `wwRenderVoltageReferenceBlock`,
    `wwWirePerUnitProfileFieldsEvents`) were removed with the modal.
    The three-concept presentation now lives exclusively in the per-unit
    details popover (`wwRenderChannelPerUnitResolution`), which is unchanged."""

    def test_sd_modal_preview_helpers_are_gone(self):
        source = _source()
        assert 'function wwPerUnitEffectiveVoltageBaseLines(' not in source
        assert 'function wwRenderVoltageReferenceBlock(' not in source
        assert 'function wwWirePerUnitProfileFieldsEvents()' not in source

    def test_popover_presentation_helpers_remain_for_the_same_concepts(self):
        """The popover still renders Nominal voltage / Channel
        interpretation / Effective base for every PU-configured channel
        via `wwRenderChannelPerUnitResolution`.  The popover uses the
        row-helper form (`wwPerUnitInfoRowHtml("Nominal voltage", ...)`)
        rather than the SD modal's string-concatenation form."""
        source = _source()
        assert 'function wwRenderChannelPerUnitResolution(' in source
        assert 'wwPerUnitInfoRowHtml("Nominal voltage"' in source
        assert 'wwPerUnitInfoRowHtml("Channel interpretation"' in source
        assert '"Effective base"' in source


class TestMeasurementGroupPresentationUnchanged:
    """Checklist item 5: Measurement Group provenance rendering keeps
    its own exact prior labels/wording -- this enhancement only extends
    the SAME presentation to a second scope, never alters it."""

    def test_measurement_group_source_line_unchanged(self):
        source = _source()
        body = _function_body(
            source, "function wwRenderChannelPerUnitResolution(resolution)", "async function wwFetchChannelPerUnitResolution"
        )
        assert '"Source", "Measurement Group: "' in body

    def test_equipment_rating_row_still_measurement_group_only(self):
        source = _source()
        body = _function_body(
            source, "function wwRenderChannelPerUnitResolution(resolution)", "async function wwFetchChannelPerUnitResolution"
        )
        assert 'resolution.source_kind === "measurement_group" && resolution.equipment_rating_mva != null' in body


class TestNoUnrelatedRegressions:
    """DEC-051 precedence, Slice 4 arithmetic, and Slice 1/2/3
    navigation are all outside this presentation-only enhancement's
    scope -- confirm their own markup/entry points are untouched."""

    def test_per_unit_settings_hub_retired_rd_is_the_config_entry_point(self):
        """PU-UI-001 Slice B: the Hub is retired; RD is the new entry point."""
        source = _source()
        assert 'id="wwOpenPerUnitSettingsBtn"' not in source

    def test_coverage_hub_section_retired_banner_is_the_new_signal(self):
        """PU-UI-001 Slice B: Hub coverage section retired; Slice C banner
        (#wwPuConfigBanner) replaces it in Waveform Analysis."""
        source = _source()
        assert 'id="wwPuCoverageBody"' not in source
        assert 'id="wwPuConfigBanner"' in source

    def test_per_unit_details_popover_still_present(self):
        source = _source()
        assert 'id="wwChannelMenuPerUnitBtn"' in source
        assert 'id="wwChannelPerUnitOverlay"' in source

    def test_sd_modal_current_base_functions_removed_in_pu_ui_001(self):
        """PU-UI-001 Step B: the SD modal's own current-base arithmetic
        helpers were removed with the modal.  The corrected formula
        (Ibase = MVA / (sqrt(3) * Vbase_LL)) is now covered by the
        backend's `per_unit.py` and the group-aware service layer."""
        source = _source()
        assert 'function wwPerUnitEditorResolvedCurrentBaseText(' not in source
        assert 'function wwPerUnitDerivedCurrentBaseKa(' not in source
        assert 'async function wwOpenPerUnitProfilesModal(' not in source
