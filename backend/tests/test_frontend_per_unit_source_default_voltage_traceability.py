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


class TestEditorPreviewShowsThreeSeparateLines:
    """Checklist item 3: the Source Default editor's own read-only
    preview shows the three labels, each on its own line, matching the
    popover's own presentation of the same three concepts."""

    def test_preview_lines_use_the_three_required_labels(self):
        source = _source()
        body = _function_body(
            source, "function wwPerUnitEffectiveVoltageBaseLines(state, reference)", "function wwRenderVoltageReferenceBlock"
        )
        assert '"Nominal voltage: "' in body
        assert '"Channel interpretation: "' in body
        assert '"Effective base: "' in body

    def test_preview_returns_three_distinct_lines_not_one_combined_sentence(self):
        source = _source()
        body = _function_body(
            source, "function wwPerUnitEffectiveVoltageBaseLines(state, reference)", "function wwRenderVoltageReferenceBlock"
        )
        # Three array elements, never string-concatenated into one.
        assert body.count("Nominal voltage: \" + vbase") == 1
        assert body.count("Channel interpretation: \" + interpretation") == 1
        assert body.count("Effective base: \" + effective.toFixed(2)") == 1

    def test_preview_renders_each_line_as_its_own_hint_div(self):
        source = _source()
        body = _function_body(source, "function wwRenderVoltageReferenceBlock(state)", "function wwWirePerUnitProfileFieldsEvents")
        assert "const previewLinesHtml = (lines) =>" in body
        assert 'lines.map((line) => \'<div class="hint">\'' in body


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

    def test_per_unit_settings_entry_point_still_present(self):
        source = _source()
        assert 'id="wwOpenPerUnitSettingsBtn"' in source

    def test_coverage_section_still_present(self):
        source = _source()
        assert 'id="wwPuCoverageBody"' in source

    def test_per_unit_details_popover_still_present(self):
        source = _source()
        assert 'id="wwChannelMenuPerUnitBtn"' in source
        assert 'id="wwChannelPerUnitOverlay"' in source

    def test_current_base_preview_formula_still_uses_raw_vbase(self):
        source = _source()
        assert "sbaseVa / (PER_UNIT_SQRT_3 * vbaseVolts)" in source
