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

    def test_line_phase_voltage_icon_uses_the_owner_asset_not_inline_svg(self):
        """Branding update (owner ticket): the Line/Phase Voltage tool
        nav item's former hand-drawn inline <svg> is replaced by a
        data-ww-icon placeholder resolving to the owner-supplied
        frontend/assets/icons/calculator/delta_Y.svg, the same
        mask-image registry mechanism the Analysis/Compliance pages'
        own type-nav icons already use -- never a redrawn icon, never a
        second icon system. Label, calculation logic, click handler,
        aria-controls, aria-current and layout are all untouched."""
        source = _source()
        page = _calculator_page(source)
        btn = _function_body(page, 'id="wwCalcToolLinePhaseBtn"', "</button>")
        assert "<svg" not in btn
        assert 'data-ww-icon="CALCULATOR_LINE_PHASE_VOLTAGE"' in btn
        assert 'class="ww-analysis-type-icon" aria-hidden="true"' in btn
        assert 'aria-controls="wwCalcToolLinePhase"' in btn
        assert '<span class="ww-analysis-type-label">Line / Phase Voltage</span>' in btn

        registry_idx = source.index("const WW_TOOL_ICONS = {")
        registry = source[registry_idx : source.index("};", registry_idx)]
        assert 'CALCULATOR_LINE_PHASE_VOLTAGE: "assets/icons/calculator/delta_Y.svg",' in registry
        asset_path = FRONTEND.parent / "assets" / "icons" / "calculator" / "delta_Y.svg"
        assert asset_path.is_file()

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
        assert "wwLineToLinePairHtml(" in calc_block
        assert "wwLineToLinePairSvg(" in calc_block
        # Phase-to-neutral quantities (inputs, Balanced L-N, formula operands,
        # diagram vectors) go through the shared phase-to-neutral helpers.
        assert "wwPhaseToNeutralVoltageHtml(" in calc_block
        assert "wwPhaseToNeutralVoltageSvg(" in calc_block
        assert "wwLineToLinePhaseToNeutralFormulaHtml(" in calc_block
        # The angle label is the phase angle: V<sub>R</sub>, not V<sub>RN</sub>.
        assert 'wwPhaseVoltageHtml(phase.canonical, pd) + " angle (degrees)"' in calc_block
        for forbidden in ('"-N"', "'-N'", "V" + "_R", "V" + "_RY", "V" + "_RN"):
            assert forbidden not in calc_block, forbidden

    def test_calculator_static_phase_labels_use_plain_phase_to_neutral_fallback(self):
        page = _calculator_page(_source())
        for key in "RYB":
            assert f'id="wwCalcPhase{key}Label">V{key}N</span>' in page
            assert f'id="wwCalcMag{key}Label">V{key}N magnitude</span>' in page
            assert f'id="wwCalcAngle{key}Label">V{key} angle (degrees)</span>' in page
            # Never the hyphenated or underscore forms.
            assert f">{key}-N" not in page
            assert "V" + "_" + key not in page

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


def _calc_block(source: str) -> str:
    return _function_body(
        source,
        "const WW_CALCULATOR_RYB_PHASE_DISPLAY",
        "// ==================================================================\n        // Compliance",
    )


class TestPowerCurrentCalculator:
    """Power & Current: the second Calculator tool (Current / P-Q-S / Power
    Factor internal tabs). Frontend-local like Line / Phase Voltage."""

    def test_nav_item_sits_directly_below_line_phase_voltage_with_the_owner_icon(self):
        page = _calculator_page(_source())
        nav = _function_body(page, 'class="ww-analysis-type-nav ww-calculator-tool-nav"', "</nav>")
        line = nav.index('id="wwCalcToolLinePhaseBtn"')
        power = nav.index('id="wwCalcToolPowerCurrentBtn"')
        assert line < power
        assert nav.count('class="ww-analysis-type-item') == 2
        assert 'aria-controls="wwCalcToolPowerCurrent"' in nav
        assert 'data-ww-icon="CALCULATOR_POWER_CURRENT"' in nav
        assert 'class="ww-analysis-type-label">Power &amp; Current</span>' in nav
        # The owner icon goes through the registry, never an inline <svg>.
        assert "<svg" not in _function_body(nav, 'id="wwCalcToolPowerCurrentBtn"', "</button>")

    def test_icon_is_registered_and_listed_in_the_manifest(self):
        import json

        source = _source()
        assert 'CALCULATOR_POWER_CURRENT: "assets/icons/calculator/amparent_square.svg",' in source
        manifest = json.loads((FRONTEND.parent / "assets" / "icons" / "manifest.json").read_text(encoding="utf-8"))
        entry = manifest["CALCULATOR_POWER_CURRENT"]
        assert entry["file"] == "calculator/amparent_square.svg"
        assert entry["source"] == "owner-supplied"
        assert (FRONTEND.parent / "assets" / "icons" / entry["file"]).is_file()

    def test_panel_is_hidden_by_default_inside_the_same_calculator_workspace(self):
        page = _calculator_page(_source())
        assert 'id="wwCalcToolPowerCurrent" aria-label="Power &amp; Current calculator" hidden>' in page
        assert "<h3>Power &amp; Current</h3>" in page
        assert "Power, current, and power-factor calculations for common electrical engineering use cases." in page
        # One page, internal tabs -- no second page route.
        assert 'id="pagePowerCurrent"' not in page

    def test_three_internal_tabs_with_tab_roles_and_panels(self):
        page = _calculator_page(_source())
        assert 'role="tablist"' in page
        tab_end = page.index("</span>", page.index('id="wwPcTabList"'))
        tablist = page[page.index('id="wwPcTabList"'):tab_end]
        for button, tab, label, panel in (
            ("wwPcTabCurrentBtn", "current", "Current", "wwPcCurrentPanel"),
            ("wwPcTabPqsBtn", "pqs", "P-Q-S", "wwPcPqsPanel"),
            ("wwPcTabPfBtn", "pf", "Power Factor", "wwPcPfPanel"),
        ):
            assert f'id="{button}" data-pc-tab="{tab}" role="tab"' in tablist
            assert f'aria-controls="{panel}">{label}</button>' in tablist
            assert f'id="{panel}" role="tabpanel" aria-labelledby="{button}"' in page
        assert tablist.index("wwPcTabCurrentBtn") < tablist.index("wwPcTabPqsBtn") < tablist.index("wwPcTabPfBtn")
        # Only the Current tab is initially shown.
        assert 'id="wwPcPqsPanel" role="tabpanel" aria-labelledby="wwPcTabPqsBtn" hidden>' in page
        assert 'id="wwPcPfPanel" role="tabpanel" aria-labelledby="wwPcTabPfBtn" hidden>' in page

    def test_current_tab_controls_and_default_example(self):
        page = _calculator_page(_source())
        for token in (
            'id="wwPcSystemSingleBtn"',
            'id="wwPcSystemThreeBtn"',
            'id="wwPcVoltage" min="0" step="any" value="132"',
            '<option value="V">V</option>',
            '<option value="kV" selected>kV</option>',
            'id="wwPcCurrentS" min="0" step="any" value="100"',
            '<option value="VA">VA</option>',
            '<option value="kVA">kVA</option>',
            '<option value="MVA" selected>MVA</option>',
            'id="wwPcCurrentValue"',
            'id="wwPcCurrentFormula"',
        ):
            assert token in page, token

    def test_pqs_and_power_factor_controls_and_units(self):
        page = _calculator_page(_source())
        for token in (
            'id="wwPqsP"', 'id="wwPqsQ"', 'id="wwPqsS"', 'id="wwPqsResultBody"', 'id="wwPqsFormula"',
            'id="wwPfValue"', 'id="wwPfLaggingBtn"', 'id="wwPfLeadingBtn"',
            'id="wwPfP"', 'id="wwPfQ"', 'id="wwPfS"', 'id="wwPfResultBody"', 'id="wwPfFormula"',
            '<option value="W">W</option>', '<option value="kW">kW</option>', '<option value="MW" selected>MW</option>',
            '<option value="var">var</option>', '<option value="kvar">kvar</option>', '<option value="MVAr" selected>MVAr</option>',
            "Lagging / Inductive", "Leading / Capacitive",
        ):
            assert token in page, token
        # Calculated fields are tagged, never silently overwritten.
        for key in ("wwPqsPTag", "wwPqsQTag", "wwPqsSTag", "wwPfPTag", "wwPfQTag", "wwPfSTag"):
            assert f'id="{key}" hidden>calculated</span>' in page

    def test_unit_normalisation_is_a_single_factor_table(self):
        block = _calc_block(_source())
        table = _function_body(block, "const WW_PC_UNIT_FACTORS = Object.freeze({", "});")
        for entry in ("V: 1, kV: 1e3", "W: 1, kW: 1e3, MW: 1e6", "var: 1, kvar: 1e3, MVAr: 1e6", "VA: 1, kVA: 1e3, MVA: 1e6"):
            assert entry in table
        assert "function wwPcReadBase(" in block
        assert "function wwPcFromBase(" in block

    def test_formulas_are_implemented(self):
        block = _calc_block(_source())
        current = _function_body(block, "function wwPcSolveCurrent(", "function wwPcSolvePqs(")
        assert 'system === "three" ? Math.sqrt(3) * voltage.value : voltage.value' in current
        assert "apparent.value / denominator" in current
        pqs = _function_body(block, "function wwPcSolvePqs(", "function wwPcSolvePf(")
        assert "Math.hypot(P, Q)" in pqs
        assert "wwPcLeg(S, P)" in pqs and "wwPcLeg(S, Q)" in pqs
        assert "Math.abs(P) / S" in pqs
        pf = _function_body(block, "function wwPcSolvePf(", "function wwPcFormulaHtml(")
        assert "P = S * f;" in pf
        assert "Math.sqrt(1 - f * f)" in pf
        assert "S = Math.abs(P) / f;" in pf
        assert "Math.tan(Math.acos(f))" in pf
        assert "S = qAbs / Math.sin(Math.acos(f));" in pf
        assert 'const sign = pfType === "leading" ? -1 : 1;' in pf

    def test_validation_rules_are_encoded(self):
        block = _calc_block(_source())
        assert '"Voltage must be greater than zero."' in block
        assert '"Apparent power cannot be negative."' in block
        assert '"|P| cannot be greater than S."' in block
        assert '"|Q| cannot be greater than S."' in block
        assert '"Power factor must be greater than 0 and no more than 1."' in block
        assert "pf.value > 0 && pf.value <= 1" in block
        assert '"At PF = 1, Q must be zero."' in block
        assert "f === 1 ? 0" in block
        assert '"Result is out of range."' in block
        assert "Number.isFinite" in block

    def test_tab_state_helpers_and_keyboard_support(self):
        block = _calc_block(_source())
        for fn in (
            "function wwPcSetTab(", "function wwPcTabKeydown(", "function wwPcSetSystem(",
            "function wwPcSetPfType(", "function wwCalcSetTool(", "function wwPcRender(",
        ):
            assert fn in block, fn
        keydown = _function_body(block, "function wwPcTabKeydown(", "function wwPcSetPressedPair(")
        for key in ("ArrowRight", "ArrowLeft", "Home", "End"):
            assert f'"{key}"' in keydown
        # Inactive panels are only hidden, so entered values survive tab switches.
        assert "document.getElementById(panelId).hidden = !active;" in block
        # Rendering is driven from the existing Calculator render entry point.
        assert "wwPcRender();" in _function_body(block, "function wwCalcRender()", "function wwCalcRenderLabels()")

    def test_line_phase_voltage_still_defaults_to_the_active_tool(self):
        page = _calculator_page(_source())
        assert 'class="ww-analysis-type-item active" id="wwCalcToolLinePhaseBtn" aria-current="true"' in page
        assert 'id="wwCalcToolLinePhase" aria-label="Line / Phase Voltage calculator">' in page

    def test_line_to_line_symbol_uses_the_shared_formatter_only(self):
        source = _source()
        assert 'const WW_GENERIC_LL_SUBSCRIPT = "LL";' in source
        block = _calc_block(source)
        assert 'wwElectricalSymbolHtml("V", "LL")' in block
        assert "V_LL" not in block
        assert "V_LL" not in _calculator_page(source)

    def test_power_current_is_frontend_local(self):
        source = _source()
        block = _calc_block(source)
        page = _calculator_page(source)
        for forbidden in ("fetch(", "/api/v1", "localStorage", "sessionStorage", "XMLHttpRequest"):
            assert forbidden not in block, forbidden
            assert forbidden not in page, forbidden
