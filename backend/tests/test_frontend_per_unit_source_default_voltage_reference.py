"""Static regression checks for the Per-Unit Configuration Slice 4
frontend fixes (frontend/index.html) -- the Source Default modal's own
cosmetic previews and copy must match the corrected backend arithmetic
(app.domain.per_unit.resolve_per_unit()'s VOLTAGE branch, Slice 4).

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


class TestCurrentBasePreviewNoLongerDoubleAdjustsForLg:
    """The cosmetic "Calculated Current Base" preview must match the
    corrected backend formula: Vbase_LL is now always the raw entered
    value, never multiplied by sqrt(3) for a line-to-ground reference."""

    def test_derived_branch_never_multiplies_by_sqrt3_for_lg(self):
        source = _source()
        body = _function_body(
            source, "function wwPerUnitEditorResolvedCurrentBaseText(state)", "async function wwOpenPerUnitProfilesModal"
        )
        derived_branch = body[body.index('state.currentBaseMode === "derived"'):]
        assert "PER_UNIT_LINE_TO_GROUND" not in derived_branch
        assert "vbaseLL" not in derived_branch

    def test_derived_branch_still_computes_ibase_from_raw_vbase(self):
        source = _source()
        body = _function_body(
            source, "function wwPerUnitEditorResolvedCurrentBaseText(state)", "async function wwOpenPerUnitProfilesModal"
        )
        assert "sbaseVa / (PER_UNIT_SQRT_3 * vbaseVolts)" in body


class TestVoltageReferenceTooltipNoLongerMisleading:
    """The old tooltip claimed voltage reference is "never applied
    automatically to a displayed channel's own per-unit value" -- false
    since Slice 4. It must now accurately describe the corrected
    division."""

    def test_stale_never_applied_claim_is_gone(self):
        source = _source()
        assert "never applied automatically to a displayed channel's own per-unit value" not in source

    def test_tooltip_describes_the_corrected_division(self):
        source = _source()
        body = _function_body(source, "function wwRenderVoltageReferenceBlock(state)", "if (state.voltageReferenceMode")
        assert "Vbase_LL / √3" in body or "Vbase_LL" in body


class TestEffectiveVoltageBasePreview:
    """The task's own optional (but implemented here) secondary
    preview: "Nominal system voltage: 275 kV L-L — Effective L-G base:
    158.77 kV"-shaped text, shown once both the base and reference are
    known."""

    def test_preview_helper_exists_and_never_fabricates_without_both_inputs(self):
        source = _source()
        body = _function_body(
            source, "function wwPerUnitEffectiveVoltageBaseText(state, reference)", "function wwRenderVoltageReferenceBlock"
        )
        assert "return null" in body
        assert "PER_UNIT_LINE_TO_GROUND" in body
        assert "PER_UNIT_SQRT_3" in body

    def test_preview_is_wired_into_both_manual_and_auto_branches(self):
        source = _source()
        body = _function_body(source, "function wwRenderVoltageReferenceBlock(state)", "function wwWirePerUnitProfileFieldsEvents")
        assert "wwPerUnitEffectiveVoltageBaseText(state, state.voltageReferenceOverride)" in body
        assert "wwPerUnitEffectiveVoltageBaseText(state, state.autoDetection.reference)" in body

    def test_preview_line_is_html_escaped(self):
        source = _source()
        body = _function_body(source, "function wwRenderVoltageReferenceBlock(state)", "function wwWirePerUnitProfileFieldsEvents")
        assert "escapeHtml(manualPreview)" in body
        assert "escapeHtml(autoPreview)" in body


class TestSlice1Through3NavigationUnaffected:
    """This slice is a calculation/copy fix only -- Slice 1-3's own
    structure (Per-Unit Settings hierarchy, coverage, traceability) must
    remain completely intact."""

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
