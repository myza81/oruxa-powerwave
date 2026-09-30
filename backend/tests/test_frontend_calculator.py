"""Static structural regression checks for the first-class Calculator page."""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _function_body(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


def _calculator_page(source: str) -> str:
    start = source.index('<section id="pageCalculator"')
    end = source.index('<section id="pageDataPreparation"', start)
    return source[start:end]


class TestCalculatorTopLevelNav:
    def test_calculator_nav_button_exists_after_compliance(self):
        source = _source()
        nav_list = _function_body(source, 'class="shell-nav-list"', 'class="shell-nav-bottom"')
        compliance_index = nav_list.index('id="mainNavComplianceBtn"')
        calculator_index = nav_list.index('id="mainNavCalculatorBtn"')
        assert compliance_index < calculator_index
        assert '<span class="shell-nav-label">Calculator</span>' in nav_list

    def test_full_main_nav_order_includes_calculator_after_compliance(self):
        source = _source()
        nav_list = _function_body(source, 'class="shell-nav-list"', 'class="shell-nav-bottom"')
        labels = [
            "Recordings",
            "Waveform",
            "Table",
            "Calculated Channels",
            "Analysis",
            "Compliance",
            "Calculator",
        ]
        positions = [nav_list.index(f'<span class="shell-nav-label">{label}</span>') for label in labels]
        assert positions == sorted(positions)

    def test_shellSetCurrentPage_handles_calculator_page(self):
        source = _source()
        assert 'page !== "calculator"' in source
        assert 'document.getElementById("pageCalculator").hidden = page !== "calculator";' in source
        assert 'setShellNavCurrent("mainNavCalculatorBtn", page === "calculator")' in source
        assert (
            'document.getElementById("mainNavCalculatorBtn").addEventListener'
            '("click", () => shellSetCurrentPage("calculator"));'
        ) in source


class TestCalculatorPageShell:
    def test_calculator_page_exists_hidden_with_line_phase_voltage_tool(self):
        source = _source()
        assert '<section id="pageCalculator" aria-label="Calculator" hidden>' in source
        page = _calculator_page(source)
        assert "<h2>Calculator</h2>" in page
        assert "Quick electrical engineering calculations without requiring an event recording." in page
        assert 'class="ww-analysis-shell ww-calculator-workspace"' in page
        assert 'class="ww-analysis-type-nav ww-calculator-tool-nav"' in page
        assert 'class="ww-analysis-type-item active"' in page
        assert 'class="ww-analysis-type-icon"' in page
        assert 'class="ww-analysis-type-label">Line / Phase Voltage</span>' in page
        assert 'class="ww-analysis-content panel ww-phasor-panel ww-calculator-tool"' in page
        assert 'id="wwCalcToolLinePhaseBtn"' in page
        assert 'id="wwCalcToolLinePhase"' in page
        assert "Line / Phase Voltage" in page
        assert "wwCalcBalancedPanel" in page
        assert "wwCalcIndividualPanel" in page

    def test_line_phase_voltage_controls_exist(self):
        source = _source()
        page = _calculator_page(source)
        for token in (
            'id="wwCalcModeBalancedBtn"',
            'id="wwCalcModeIndividualBtn"',
            'class="ww-oc-axis-toggle-group"',
            'class="ww-oc-axis-toggle-btn ww-oc-axis-toggle-btn--active"',
            'id="wwCalcBalancedDirection"',
            'id="wwCalcBalancedMagnitude"',
            'id="wwCalcBalancedUnit"',
            'id="wwCalcIndividualUnit"',
            'id="wwCalcMagR"',
            'id="wwCalcAngleR"',
            'id="wwCalcMagY"',
            'id="wwCalcAngleY"',
            'id="wwCalcMagB"',
            'id="wwCalcAngleB"',
            'id="wwCalcBalancedDiagram"',
            'id="wwCalcIndividualDiagram"',
            'id="wwCalcBalancedFormula"',
            'id="wwCalcIndividualFormula"',
        ):
            assert token in page

    def test_line_phase_voltage_uses_dense_workspace_sections(self):
        source = _source()
        page = _calculator_page(source)
        for token in (
            'class="ww-calculator-balanced-top"',
            'class="ww-calculator-balanced-inputs"',
            'class="ww-calculator-support-grid"',
            'class="ww-calculator-individual-top"',
            'aria-label="Balanced voltage result"',
            'aria-label="Line voltage results"',
        ):
            assert token in page

    def test_required_calculator_functions_exist(self):
        source = _source()
        for fn in (
            "function wwCalcPolarToComplex(",
            "function wwCalcSubtractComplex(",
            "function wwCalcComplexToPolar(",
            "function wwCalcNormalizeAngleDeg(",
            "function wwCalcRenderBalanced(",
            "function wwCalcRenderIndividual(",
            "function wwCalcRenderDiagram(",
            "function wwCalculatorInit(",
        ):
            assert fn in source

    def test_calculator_uses_shared_electrical_formatters_for_symbols(self):
        source = _source()
        calc_block = _function_body(source, "const WW_CALCULATOR_RYB_PHASE_DISPLAY", "// ==================================================================\n        // Compliance")
        assert "wwRoleLabelHtml(" in calc_block
        assert "wwLineToLinePairHtml(" in calc_block
        assert "wwLineToLineFormulaHtml(" in calc_block
        assert "wwRoleLabelSvg(" in calc_block
        assert "wwLineToLinePairSvg(" in calc_block
        assert "V_R" not in calc_block
        assert "V_RY" not in calc_block

    def test_calculator_scope_excludes_unrequested_functions(self):
        source = _source()
        page = _calculator_page(source)
        calc_block = _function_body(source, "const WW_CALCULATOR_RYB_PHASE_DISPLAY", "// ==================================================================\n        // Compliance")
        for forbidden in (
            "Star",
            "Delta",
            "P/Q/S",
            "sequence-component",
            "/api/v1",
            "fetch(",
        ):
            assert forbidden not in page
            assert forbidden not in calc_block

    def test_calculator_page_does_not_touch_analysis_compliance_or_backend_state(self):
        source = _source()
        nav_fn = _function_body(source, "function shellSetCurrentPage(page)", "// The (responsive-only)")
        assert "wwAnalysisLoadContexts" not in nav_fn
        assert "wwComplianceLoadGroups" not in nav_fn
        assert "wwCalcRender();" in nav_fn
        assert "fetch(" not in _calculator_page(source)
