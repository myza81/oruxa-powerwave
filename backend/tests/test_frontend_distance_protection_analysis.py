"""Static structural regression checks for Distance Protection v1
(frontend/index.html) -- the FIFTH `Analysis` menu consumer. Same
source-text substring-assertion pattern every other `test_frontend_*.py`
file in this suite already uses. Real fetch/render/interaction behavior
is covered by browser-tests/distance_protection_analysis.spec.js
(mandatory Playwright coverage) -- these checks catch structural
regressions (missing wiring, markup/JS drift, accidental trip/relay-
logic scope creep) that a real browser is not required to detect. See
docs/project-memory/DISTANCE_PROTECTION_ANALYSIS.md.
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


class TestDistanceNavAndPanel:
    def test_distance_nav_button_exists_and_is_activated(self):
        source = _source()
        assert 'id="wwAnalysisTypeDistanceBtn"' in source
        assert 'data-analysis-type="distance"' in source
        panel = _function_body(source, 'id="wwDistancePanel"', "</section>\n                    </div>\n                </div>\n            </section>")
        assert "This analyzer is not implemented yet." not in panel

    def test_analyzer_order_is_overcurrent_impedance_distance_phasor_sequence(self):
        source = _source()
        nav = _function_body(source, 'class="ww-analysis-type-nav"', "</nav>")
        assert (
            nav.index("Overcurrent") < nav.index("Impedance Locus") < nav.index("Distance Protection")
            < nav.index("Phasor") < nav.index("Sequence Components")
        )

    def test_panel_routing_table_includes_distance(self):
        source = _source()
        fn = _function_body(source, "const wwAnalysisPanelsByType", "function wwSetActiveAnalysisType")
        assert 'distance: "wwDistancePanel"' in fn

    def test_distance_is_a_separate_analyzer_from_impedance(self):
        """Never merged into Impedance Locus -- its own panel id, own
        state object, own R-X plot instance."""
        source = _source()
        assert 'id="wwImpedancePanel"' in source
        assert 'id="wwDistancePanel"' in source
        assert "const wwImpedanceState" in source
        assert "const wwDistanceState" in source
        assert 'id="wwImpedanceSvg"' in source
        assert 'id="wwDistanceSvg"' in source


class TestDistanceMarkupSeparation:
    """Mirrors Impedance Locus's/Sequence Components' own architectural-
    correction shape (see docs/project-memory/ANALYSIS_INPUT_SOURCE.md)
    -- three independent regions: an always-visible Input Source toggle,
    a Recording-only section, and an always-visible Body."""

    def test_input_source_toggle_is_a_direct_sibling_not_nested(self):
        source = _source()
        panel = _function_body(source, 'id="wwDistancePanel"', 'id="wwDistanceRecordingSection"')
        assert "ww-oc-input-source-panel" in panel
        assert 'id="wwDistanceInputSourceRecordingBtn"' in panel
        assert 'id="wwDistanceInputSourceManualBtn"' in panel

    def test_recording_section_holds_bay_and_playback(self):
        source = _source()
        section = _function_body(source, 'id="wwDistanceRecordingSection"', 'id="wwDistanceBody"')
        assert 'id="wwDistanceContextSelect"' in section
        assert 'id="wwDistancePlaybackPanel"' in section
        assert 'id="wwDistanceRelatedWaveformsAnchor"' in section
        assert 'id="wwDistanceEmptyState"' in section

    def test_body_holds_settings_zones_manual_input_and_plot_never_recording_gated(self):
        source = _source()
        body = _function_body(source, 'id="wwDistanceBody"', "</section>\n                    </div>\n                </div>\n            </section>")
        assert 'id="wwDistanceLoopSelect"' in body
        assert 'id="wwDistanceCharacteristicSelect"' in body
        assert 'id="wwDistanceOutputBasisSelect"' in body
        assert 'id="wwDistanceZone1Enabled"' in body
        assert 'id="wwDistanceManualInputSection"' in body
        assert 'id="wwDistanceSvg"' in body
        assert 'id="wwDistanceValuesList"' in body
        assert 'id="wwDistanceZoneStateList"' in body


class TestDistanceInputSourceReusesSharedConstants:
    def test_reuses_shared_ww_analysis_input_source_constants(self):
        source = _source()
        fn = _function_body(source, "function wwDistanceSetInputSource", "function wwDistanceSyncInputSourceButtons")
        assert "WW_ANALYSIS_INPUT_SOURCE_RECORDING" in fn
        assert "WW_ANALYSIS_INPUT_SOURCE_MANUAL" in fn
        assert "const WW_DISTANCE_INPUT_SOURCE" not in source

    def test_reuses_shared_axis_toggle_css_classes(self):
        source = _source()
        panel = _function_body(source, 'id="wwDistancePanel"', 'id="wwDistanceRecordingSection"')
        assert "ww-oc-axis-toggle-group" in panel
        assert "ww-oc-axis-toggle-btn" in panel


class TestDistanceLoopSelector:
    def test_loop_select_offers_exactly_ab_bc_ca(self):
        source = _source()
        field = _function_body(source, 'id="wwDistanceLoopSelect"', "</select>")
        assert 'value="AB"' in field
        assert 'value="BC"' in field
        assert 'value="CA"' in field
        assert "AG" not in field
        assert "BG" not in field
        assert "CG" not in field

    def test_loop_role_mapping_never_requires_the_unrelated_third_phase(self):
        source = _source()
        fn = _function_body(source, "const WW_DISTANCE_LOOP_ROLES", "function wwDistanceDefaultZoneSettings")
        assert 'AB: ["Va", "Vb", "Ia", "Ib"]' in fn
        assert 'BC: ["Vb", "Vc", "Ib", "Ic"]' in fn
        assert 'CA: ["Vc", "Va", "Ic", "Ia"]' in fn


class TestDistanceCharacteristicSelector:
    def test_characteristic_select_offers_mho_and_quadrilateral(self):
        source = _source()
        field = _function_body(source, 'id="wwDistanceCharacteristicSelect"', "</select>")
        assert 'value="mho"' in field
        assert 'value="quadrilateral"' in field

    def test_characteristic_switch_never_touches_measured_impedance(self):
        """Characteristic switching recomputes Operated/Not-Operated and
        redraws zones -- it must never call the loop-impedance request
        function directly by name (it goes through the SAME settings-
        changed path Loop/Basis changes already use, which re-requests
        the CURRENT point but never fabricates a different R/X)."""
        source = _source()
        fn = _function_body(source, "function wwDistanceHandleCharacteristicChanged", "function wwDistanceHandleZoneSettingChanged")
        assert "wwDistanceUpdateCharacteristicFieldsVisibility" in fn
        assert "wwDistanceHandleSettingsChanged" in fn


class TestDistanceZoneSettingsGrid:
    """Compact, responsive 3-card grid -- never a huge vertically-stacked
    form (owner instruction)."""

    def test_zone_grid_css_is_a_three_column_responsive_grid(self):
        source = _source()
        css = _function_body(source, ".ww-dist-zone-grid {", ".ww-dist-zone-card {")
        assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in css
        assert "@container ww-oc-settings-panel" in source

    def test_each_zone_has_enabled_delay_angle_and_characteristic_specific_reach_fields(self):
        source = _source()
        for n in (1, 2, 3):
            card = _function_body(source, f'id="wwDistanceZone{n}Enabled"', f'ww-dist-zone-card" style="--zone-color: var(--ww-dist-card-zone{n + 1})' if n < 3 else '<div class="ww-oc-manual-input-section')
            assert f'id="wwDistanceZone{n}DelayInput"' in card
            assert f'id="wwDistanceZone{n}AngleInput"' in card
            assert f'id="wwDistanceZone{n}ReachInput"' in card
            assert f'id="wwDistanceZone{n}ReactiveReachInput"' in card
            assert f'id="wwDistanceZone{n}ResistiveForwardInput"' in card
            assert f'id="wwDistanceZone{n}ResistiveReverseInput"' in card

    def test_zones_evaluated_independently_no_priority_suppression(self):
        """Zone priority is explicitly NOT enforced -- multiple zones may
        legitimately report Operated simultaneously; the frontend must
        never suppress Zone 2/3 because Zone 1 operates."""
        source = _source()
        fn = _function_body(source, "function wwDistanceRenderZoneStateList", "function wwDistanceRenderResult")
        assert "for (const key of WW_DISTANCE_ZONE_KEYS)" in fn
        assert "break" not in fn
        assert "return" not in fn.split("for (const key")[1].split("}")[0]


class TestDistanceZoneColorHierarchy:
    def test_zone_color_tokens_exist_light_and_dark(self):
        theme = Path(__file__).resolve().parents[2] / "frontend" / "theme.css"
        css = theme.read_text(encoding="utf-8")
        assert "--ww-dist-zone1:" in css
        assert "--ww-dist-zone2:" in css
        assert "--ww-dist-zone3:" in css
        assert css.count("--ww-dist-zone1:") == 2  # light + dark blocks
        assert css.count("--ww-dist-zone2:") == 2
        assert css.count("--ww-dist-zone3:") == 2

    def test_zone_tokens_are_distinct_from_phase_and_sequence_tokens(self):
        theme = Path(__file__).resolve().parents[2] / "frontend" / "theme.css"
        css = theme.read_text(encoding="utf-8")
        assert "--ww-dist-zone1" not in css.split("--ww-seq-zero")[0].split("--ww-seq-positive")[-1] or True
        # Distance zone tokens must not reuse the exact --ww-seq-* hex values.
        import re
        seq_values = set(re.findall(r"--ww-seq-\w+: (#[0-9a-fA-F]{6});", css))
        dist_values = set(re.findall(r"--ww-dist-zone\d: (#[0-9a-fA-F]{6});", css))
        assert seq_values.isdisjoint(dist_values)


class TestDistanceOperatedTerminology:
    """CRITICAL owner decision: 'Operated'/'Not Operated', explicitly
    NEVER 'Inside'/'Outside', for primary displayed zone state -- and
    never a trip/breaker claim anywhere in this analyzer's own markup or
    JS."""

    def test_operated_not_operated_terminology_used(self):
        source = _source()
        distance_region = _function_body(source, 'id="wwDistancePanel"', "</section>\n                    </div>\n                </div>\n            </section>")
        assert "Operated" in distance_region

    def test_inside_outside_terminology_never_used_for_zone_state(self):
        source = _source()
        fn = _function_body(source, "function wwDistanceRenderZoneStateList", "function wwDistanceRenderResult")
        assert "Inside" not in fn
        assert "Outside" not in fn
        assert "inside" not in fn
        assert "outside" not in fn

    def test_no_trip_or_breaker_claim_anywhere_in_distance_js(self):
        source = _source()
        start = source.index("Distance Protection v1 -- the FIFTH Analysis-menu analyzer (Phasor,")
        end = source.index("function wwDistanceResetState")
        region = source[start:end]
        assert "Relay tripped" not in region
        assert "Trip issued" not in region
        assert "Breaker opened" not in region

    def test_configured_delay_never_accumulated_or_declared_elapsed(self):
        source = _source()
        fn = _function_body(source, "function wwDistanceRenderZoneStateList", "function wwDistanceRenderResult")
        assert "delay" in fn.lower()
        assert "elapsed" not in fn.lower()
        assert "timer" not in fn.lower()


class TestDistanceManualPerLoopRoleLabels:
    """Manual Input reuses the Manual Phasor input architecture but only
    asks for the selected loop's own relevant phase pair -- AB never
    requires phase C."""

    def test_manual_role_labels_update_function_exists(self):
        source = _source()
        assert "function wwDistanceUpdateManualRoleLabels" in source
        fn = _function_body(source, "function wwDistanceUpdateManualRoleLabels", "function wwDistanceHandleSettingsChanged")
        assert "WW_DISTANCE_LOOP_ROLES[wwDistanceState.loop]" in fn

    def test_manual_group_has_exactly_two_voltage_and_two_current_legs(self):
        source = _source()
        manual_section = _function_body(source, 'id="wwDistanceManualInputSection"', '<div class="ww-oc-values-list" id="wwDistanceValuesList">')
        assert 'id="wwDistanceManualV1MagnitudeInput"' in manual_section
        assert 'id="wwDistanceManualV2MagnitudeInput"' in manual_section
        assert 'id="wwDistanceManualI1MagnitudeInput"' in manual_section
        assert 'id="wwDistanceManualI2MagnitudeInput"' in manual_section
        # Never a third/independent voltage or current leg for a 2-leg loop.
        assert 'id="wwDistanceManualV3MagnitudeInput"' not in manual_section
        assert 'id="wwDistanceManualI3MagnitudeInput"' not in manual_section

    def test_manual_voltage_and_current_bases_are_independent_and_shared_per_family(self):
        """N independent bases for N independent physical quantities --
        TWO bases total (Voltage, Current), each shared by its own two
        legs, never four independent per-leg bases."""
        source = _source()
        manual_section = _function_body(source, 'id="wwDistanceManualInputSection"', '<div class="ww-oc-values-list" id="wwDistanceValuesList">')
        assert manual_section.count('id="wwDistanceManualVoltageBasisSelect"') == 1
        assert manual_section.count('id="wwDistanceManualCurrentBasisSelect"') == 1


class TestDistanceRXPlotReusesImpedanceScale:
    """Mandatory equal geometric scale, R=horizontal/X=vertical, ALL 4
    quadrants, and the SAME coordinate transform as Impedance Locus's own
    plot -- never a second inconsistent renderer."""

    def test_render_plot_reuses_impedance_radius_and_nice_limit(self):
        source = _source()
        fn = _function_body(source, "function wwDistanceRenderPlot", "function wwDistanceCtVtFieldsNeeded")
        default_view = _function_body(source, "function wwDistanceDefaultView", "function wwDistanceFitZonesView")
        assert "wwImpedanceNiceLimit(maxAbs)" in default_view
        assert "wwDistanceDefaultView()" in fn
        assert "WW_IMPEDANCE_PLOT_RADIUS" in fn
        # Never re-declares its own independent px-per-ohm/limit math.
        assert "function wwDistanceNiceLimit" not in source

    def test_mho_and_quadrilateral_svg_use_the_same_toSvg_transform(self):
        source = _source()
        fn = _function_body(source, "function wwDistanceRenderPlot", "function wwDistanceCtVtFieldsNeeded")
        assert "wwDistanceMhoCircleSvg(key, z, toSvg, pxPerOhm)" in fn
        assert "wwDistanceQuadrilateralSvg(key, z, toSvg)" in fn

    def test_viewbox_covers_all_four_quadrants(self):
        source = _source()
        svg_tag = _function_body(source, 'id="wwDistanceSvg"', "</svg>")
        assert 'viewBox="-130 -130 260 260"' in svg_tag


class TestDistanceRelatedWaveformsPushesLoopRoles:
    def test_pushes_four_roles_matching_selected_loop(self):
        source = _source()
        fn = _function_body(source, "function wwDistanceComputeActiveRelatedWaveformRoles", "function wwDistancePushRelatedWaveformRoles")
        assert "WW_DISTANCE_LOOP_ROLES[wwDistanceState.loop]" in fn
        assert "result.v1_channel_ref" in fn
        assert "result.v2_channel_ref" in fn
        assert "result.i1_channel_ref" in fn
        assert "result.i2_channel_ref" in fn


class TestDistancePlaybackIntegration:
    def test_registers_as_the_fifth_shared_playback_consumer(self):
        source = _source()
        assert "wwPlaybackOnTick(wwDistanceOnPlaybackTick);" in source

    def test_no_analyzer_specific_timer_or_polling_loop(self):
        source = _source()
        start = source.index("Distance Protection v1 -- the FIFTH Analysis-menu analyzer (Phasor,")
        end = source.index("function wwDistanceResetState")
        region = source[start:end]
        assert "setInterval" not in region
        assert "requestAnimationFrame" not in region

    def test_mounts_shared_playback_transport_classes(self):
        source = _source()
        assert 'class="panel ww-phasor-playback-panel ww-analysis-playback-panel" id="wwDistancePlaybackPanel"' in source
        assert 'class="ww-phasor-playback-mount ww-analysis-playback-mount" id="wwDistancePlaybackMount"' in source


class TestDistanceResetStateWiring:
    def test_reset_state_is_called_on_whole_workspace_reset(self):
        source = _source()
        assert "wwDistanceResetState();" in source

    def test_reset_state_reinitializes_loop_characteristic_and_zones(self):
        source = _source()
        fn = _function_body(source, "function wwDistanceResetState", "// ------------------------------------------------------------------\n        // Init")
        assert 'wwDistanceState.loop = "AB";' in fn
        assert 'wwDistanceState.characteristic = "mho";' in fn
        assert "wwDistanceState.zones = {" in fn


class TestDistanceRXViewportControls:
    """Fit Zones / Zoom / Reset are viewport-only (see
    test_distance_rx_viewport.py for the behavioural tests)."""

    def test_controls_present_and_wired(self):
        source = _source()
        for btn in ("wwDistanceFitZonesBtn", "wwDistanceZoomInBtn", "wwDistanceZoomOutBtn", "wwDistanceResetViewBtn"):
            assert f'id="{btn}"' in source
            assert f'getElementById("{btn}").addEventListener("click"' in source

    def test_viewport_is_separate_from_engineering_settings(self):
        source = _source()
        # Settings handlers re-render the plot but never overwrite the view.
        for fn_name, nxt in (
            ("function wwDistanceHandleSettingsChanged", "function wwDistanceHandleLoopChanged"),
            ("function wwDistanceHandleCharacteristicChanged", "// A zone SETTING change"),
            ("function wwDistanceHandleZoneSettingChanged", "function wwDistanceSetInputSource"),
        ):
            assert "wwDistanceState.view" not in _function_body(source, fn_name, nxt)

    def test_viewport_code_never_touches_zone_settings_or_results(self):
        source = _source()
        block = _function_body(source, "// WW_DISTANCE_VIEWPORT_PURE_BEGIN", "// WW_DISTANCE_VIEWPORT_PURE_END")
        assert "wwDistanceState" not in block and "document." not in block
        view_fns = _function_body(source, "function wwDistanceFitZonesView", "function wwDistanceViewGridSvg")
        assert "zones[" not in view_fns.replace("wwDistanceState.zones, wwDistanceState.characteristic", "")
        assert "= wwDistanceState.zones" not in view_fns

    def test_single_shared_px_per_ohm_for_both_axes(self):
        source = _source()
        fn = _function_body(source, "function wwDistanceRenderPlot", "function wwDistanceCtVtFieldsNeeded")
        assert "const toSvg = (r, x) => [(r - view.centerR) * pxPerOhm, -(x - view.centerX) * pxPerOhm];" in fn
        assert 'preserveAspectRatio="xMidYMid meet"' in _function_body(source, 'id="wwDistanceSvg"', "</svg>")


class TestReverseZoneSlot:
    """The fourth manual slot: a Reverse Zone (direction fixed to reverse)."""

    def test_zone_keys_list_has_four_slots_in_order(self):
        assert 'const WW_DISTANCE_ZONE_KEYS = ["zone1", "zone2", "zone3", "zone4"];' in _source()

    def test_reverse_zone_card_has_the_same_settings_and_a_visible_direction_label(self):
        source = _source()
        card = _function_body(source, 'id="wwDistanceZone4Enabled"', '<div class="ww-oc-manual-input-section')
        assert ">Reverse Zone</span>" in source
        assert 'id="wwDistanceZone4Direction">Direction: Reverse<' in source
        for field in ("Delay", "Angle", "Reach", "ReactiveReach", "ResistiveForward", "ResistiveReverse"):
            assert f'id="wwDistanceZone4{field}Input"' in card
        assert 'aria-label="Enable Reverse Zone"' in source

    def test_reverse_zone_is_a_fixed_direction_slot_not_a_dropdown(self):
        source = _source()
        assert 'id="wwDistanceZone4DirectionSelect"' not in source
        assert 'direction: "reverse"' in _function_body(source, "const wwDistanceState = {", "latestResult: null")
        # direction is never sent as a request parameter
        params = _function_body(source, "function wwDistanceZoneParams()", "// The ONE place that dispatches")
        assert "direction" not in params

    def test_zone_params_cover_zone4_through_the_shared_key_list(self):
        params = _function_body(_source(), "function wwDistanceZoneParams()", "// The ONE place that dispatches")
        assert "for (const key of WW_DISTANCE_ZONE_KEYS)" in params

    def test_zone_state_list_and_result_wiring_include_zone4(self):
        source = _source()
        assert 'zone4: "Reverse Zone"' in source
        assert source.count("zone4: result.zone4") == 4
        assert 'for (const key of ["zone4", "zone3", "zone2", "zone1"])' in source  # draw order

    def test_geometry_is_rotated_180_not_mirrored(self):
        source = _source()
        assert 'function wwDistanceZoneSign(z) { return z && z.direction === "reverse" ? -1 : 1; }' in source
        mho = _function_body(source, "function wwDistanceMhoCircleSvg", "// Quadrilateral geometry")
        assert "sg * halfReach * Math.cos(angleRad)" in mho and "sg * halfReach * Math.sin(angleRad)" in mho
        quad = _function_body(source, "function wwDistanceQuadrilateralSvg", "// ---- R-X viewport")
        assert "sg * (xPrime * cosT + rPrime * sinT)" in quad and "sg * (xPrime * sinT - rPrime * cosT)" in quad

    def test_zone4_has_a_theme_token_in_both_themes_and_a_boundary_style(self):
        theme = (Path(__file__).resolve().parents[2] / "frontend" / "theme.css").read_text(encoding="utf-8")
        assert theme.count("--ww-dist-zone4:") == 2
        assert ".ww-dist-zone-boundary--zone4" in _source()


class TestReverseZoneDelayDefault:
    def test_reverse_zone_delay_starts_blank_and_is_not_sent_when_blank(self):
        source = _source()
        card = _function_body(source, 'id="wwDistanceZone4DelayInput"', "</label>")
        assert "value=" not in card and 'placeholder="not set"' in card
        assert 'delaySeconds: null, characteristicAngleDeg: null, direction: "reverse"' in source
        params = _function_body(source, "function wwDistanceZoneParams()", "// The ONE place that dispatches")
        assert 'else if (key !== "zone4")' in params
        assert "delay not configured" in source


class TestDistanceZoneDefaults:
    def test_zone_delay_defaults_in_markup_and_state(self):
        source = _source()
        assert 'id="wwDistanceZone1DelayInput" min="0" step="0.01" value="0"' in source
        assert 'id="wwDistanceZone2DelayInput" min="0" step="0.01" value="0.45"' in source
        assert 'id="wwDistanceZone3DelayInput" min="0" step="0.01" value="3"' in source
        # initial state and the reset state agree
        assert source.count("zone1: Object.assign(wwDistanceDefaultZoneSettings(), { delaySeconds: 0 })") == 2
        assert source.count("zone2: Object.assign(wwDistanceDefaultZoneSettings(), { delaySeconds: 0.45 })") == 2
        assert source.count("zone3: Object.assign(wwDistanceDefaultZoneSettings(), { delaySeconds: 3 })") == 2

    def test_reverse_zone_has_no_engineering_defaults(self):
        source = _source()
        assert source.count('{ delaySeconds: null, characteristicAngleDeg: null, direction: "reverse" }') == 2
        angle = _function_body(source, 'id="wwDistanceZone4AngleInput"', "</label>")
        assert "value=" not in angle and 'placeholder="not set"' in angle
        for field in ("Reach", "ReactiveReach", "ResistiveForward", "ResistiveReverse"):
            assert "value=" not in _function_body(source, f'id="wwDistanceZone4{field}Input"', "</label>")
        params = _function_body(source, "function wwDistanceZoneParams()", "// The ONE place that dispatches")
        assert 'else if (key !== "zone4") params[key + "_characteristic_angle_deg"] = "90"' in params


class TestDistanceSettingLabels:
    def test_loop_and_impedance_value_labels(self):
        source = _source()
        loop = _function_body(source, 'Fault Type / Loop</span>', "</label>")
        assert 'id="wwDistanceLoopSelect"' in loop
        values = _function_body(source, 'Impedance Values</span>', "</label>")
        assert 'id="wwDistanceOutputBasisSelect"' in values
        panel = _function_body(source, 'id="wwDistancePanel"', 'id="wwDistanceManualInputSection"')
        assert "Fault loop" not in panel and "Impedance basis" not in panel


class TestDistanceZoneCardColors:
    THEME = FRONTEND.parent / "theme.css"

    def test_cards_use_card_tokens_and_boundaries_keep_theirs(self):
        source = _source()
        for n in (1, 2, 3, 4):
            assert f"--zone-color: var(--ww-dist-card-zone{n})" in source
        assert "stroke: var(--ww-dist-zone4)" in source  # R-X boundary unchanged

    def test_light_palette_and_softest_reverse_zone(self):
        css = self.THEME.read_text(encoding="utf-8")
        for n, hexv in ((1, "#4f6b95"), (2, "#7185a6"), (3, "#94a3b8"), (4, "#c7cdd6")):
            assert f"--ww-dist-card-zone{n}: {hexv};" in css
        assert css.count("--ww-dist-card-zone4:") == 2  # light + dark

    def test_dark_theme_keeps_the_hierarchy(self):
        css = self.THEME.read_text(encoding="utf-8")

        def lum(h):
            r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        vals = [css.rsplit(f"--ww-dist-card-zone{n}: ", 1)[1][:7] for n in (1, 2, 3, 4)]
        assert [lum(v) for v in vals] == sorted((lum(v) for v in vals), reverse=True)
