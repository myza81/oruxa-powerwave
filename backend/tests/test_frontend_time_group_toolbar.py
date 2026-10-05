"""Static regression checks for TG-D1 -- migrating Zoom In/Zoom Out
(staged, X/Y split-button), Reset Time View, and Autoscale Y into each
Time Group Canvas's own local navigation toolbar.

SUPERSEDED in part by the Waveform top-toolbar migration (owner
ticket, same day): Zoom In/Out, Autoscale X/Autoscale Y and A/B
Cursors move AGAIN -- this time out of the local canvas toolbar TG-D1/
TG-D2 put them in, to page-level #wwToolbar, alongside Zoom Y
(DEC-156). TestWaveformTopToolbarMigration below covers the new
architecture; the TG-D1/TG-D2-era classes above/below it are updated
in place where they now assert the OPPOSITE (these controls are no
longer local), not deleted, so the isolation/targeting guarantees they
originally proved stay documented. A LATER Waveform toolbar
refinement ticket then moved t0 the same way and removed Synchronize
Sources outright -- see TestWaveformTopToolbarMigration's own
test_t0_migrated_sync_removed and test_frontend_time_group_sync.py's
own removal coverage. Nothing genuinely local remains in this toolbar
except the hidden Fit Selected Record stub and the (non-action) A/B/Δt
cursor values readout.

Mirrors this suite's own established pure string/index-based approach
(test_frontend_time_range_slider.py, test_frontend_time_group_canvas_empty_state.py)
-- no jsdom execution, just confirming the right gating/wiring/isolation
markers exist in the right places. Real multi-canvas isolation behavior
(a click inside Group 2 never touching Group 1) is proven live via
Playwright against a running backend -- see this task's own live-UAT
report for the full record.
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


class TestLocalToolbarShellReusesExistingStructure:
    """Task section 5: use the existing `.ww-tg-toolbar` shell from
    TG-B+C -- never a second toolbar container, never singleton ids
    reintroduced inside a repeated Time Group canvas."""

    def test_exactly_one_toolbar_container_per_canvas_template(self):
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert fn_body.count('class="ww-tg-toolbar"') == 1

    def test_local_toolbar_markup_carries_no_singleton_ids(self):
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        toolbar_start = fn_body.index('class="ww-tg-toolbar"')
        toolbar_end = fn_body.index("ww-tg-panels", toolbar_start)
        toolbar_markup = fn_body[toolbar_start:toolbar_end]
        assert ' id="' not in toolbar_markup

    def test_canvas_creation_wires_the_toolbar_exactly_once(self):
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert fn_body.count("wwWireTimeGroupToolbar(") == 1
        assert "wwWireTimeGroupToolbar(section, groupId);" in fn_body

    def test_local_toolbar_no_longer_carries_the_migrated_controls(self):
        """Waveform top-toolbar migration (owner ticket): Zoom In/Out,
        Autoscale X and Autoscale Y moved to the page-level #wwToolbar --
        the local canvas no longer duplicates them. A later Waveform
        toolbar refinement ticket moved t0 out the same way and removed
        Synchronize Sources outright -- only the hidden Fit Selected
        Record stub remains in this local toolbar now (the numeric A/B/
        Δt cursor VALUES readout stays local too, but lives in its own
        `.ww-tg-cursor-readout`, outside this toolbar div)."""
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "ww-tg-zoom-in-split" not in fn_body
        assert "ww-tg-zoom-out-split" not in fn_body
        assert "ww-tg-reset-view-btn" not in fn_body
        assert "ww-tg-autoscale-btn" not in fn_body
        assert "ww-tg-cursor-mode-btn" not in fn_body
        assert "ww-tg-t0-btn" not in fn_body
        assert "ww-tg-sync-btn" not in fn_body
        assert "ww-tg-fit-record-btn" in fn_body


class TestZoomFunctionsAcceptGroupId:
    """Task section 7: generalize wwStepZoomX()/wwStepZoomY() to accept
    a groupId, reading/writing that group's own viewport rather than
    the single workspace-wide ww.viewport."""

    def test_step_zoom_x_signature_takes_group_id_first(self):
        source = _source()
        assert "async function wwStepZoomX(groupId, direction)" in source

    def test_step_zoom_x_reads_this_groups_own_visible_range(self):
        source = _source()
        fn_idx = source.index("async function wwStepZoomX(groupId, direction)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const range = wwTimeGroupVisibleRange(groupId);" in fn_body
        assert "ww.viewport" not in fn_body

    def test_step_zoom_x_zoom_out_clamps_to_this_groups_own_bounds(self):
        source = _source()
        fn_idx = source.index("async function wwStepZoomX(groupId, direction)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwClampPanWindowToTimeGroup(groupId, next.start, next.end)" in fn_body

    def test_step_zoom_x_applies_through_the_group_scoped_viewport_call(self):
        source = _source()
        fn_idx = source.index("async function wwStepZoomX(groupId, direction)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "clearTimeout(ww.timeGroupViewportDebounceTimers.get(groupId));" in fn_body
        assert "await wwApplyAndFetchGroupViewport(groupId, next.start, next.end);" in fn_body

    def test_step_zoom_x_preserves_the_exact_stepping_factors_and_floor(self):
        """Preserve current stage sizes/numeric semantics exactly --
        task section 7's own explicit requirement."""
        source = _source()
        fn_idx = source.index("async function wwStepZoomX(groupId, direction)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        # Slice 3A (DEC-127): the stepping math lives in the shared helper.
        assert "let next = wwStepZoomXRange(range, direction);" in fn_body
        helper_idx = source.index("function wwStepZoomXRange(range, direction)")
        helper = source[helper_idx : source.index("\n        }\n", helper_idx)]
        assert "direction === \"in\" ? WW_ZOOM_STEP_IN_FACTOR : WW_ZOOM_STEP_OUT_FACTOR" in helper
        assert "Math.max(newSpan, WW_MIN_X_SPAN_SECONDS)" in helper

    def test_step_zoom_y_signature_takes_group_id_first(self):
        source = _source()
        assert "function wwStepZoomY(groupId, direction)" in source

    def test_step_zoom_y_resolves_the_active_panel_scoped_to_this_group(self):
        """Task section 9: Y zoom applies only to panels inside the
        launching Time Group -- never wwActivePanel() unscoped.
        Waveform Y-axis zoom (owner ticket): wwStepZoomY() itself is now
        a thin wrapper delegating to the shared wwStepZoomYPanel() core
        (extracted so the global, workspace-wide Y Zoom In/Out pair can
        reuse the exact same math against a DIFFERENT resolver,
        wwActivePanel(), without duplicating it) -- the resolver call
        itself (wwActivePanelForGroup(groupId), never bare
        wwActivePanel()) is unchanged."""
        source = _source()
        fn_idx = source.index("function wwStepZoomY(groupId, direction)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwStepZoomYPanel(wwActivePanelForGroup(groupId), direction);" in fn_body
        assert "wwActivePanel()" not in fn_body

    def test_step_zoom_y_preserves_exact_range_reading_and_floor_semantics(self):
        """The math itself now lives in the shared wwStepZoomYPanel()
        core (Waveform Y-axis zoom, owner ticket) -- same semantics,
        extracted not duplicated."""
        source = _source()
        fn_idx = source.index("function wwStepZoomYPanel(panel, direction)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "fl && fl.yaxis ? fl.yaxis.range : null" in fn_body
        assert "Math.max(newSpan, WW_MIN_Y_SPAN)" in fn_body
        assert '"yaxis.autorange": false' in fn_body


class TestActivePanelForGroupExcludesOtherGroups:
    """Task section 9: 'ensure unrelated groups are excluded' -- the
    per-group fallback must never resolve to ww.panels[0] outright,
    which could belong to a different Time Group."""

    def test_falls_back_to_the_first_panel_belonging_to_this_group_only(self):
        source = _source()
        fn_idx = source.index("function wwActivePanelForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwPanelTimeGroupId(active) === groupId" in fn_body
        assert "ww.panels.find((p) => wwPanelTimeGroupId(p) === groupId)" in fn_body
        assert "ww.panels[0]" not in fn_body

    def test_never_mutates_the_global_active_panel_pointer(self):
        """A group-scoped fallback lookup must not have the side effect
        of reassigning ww.activePanelGroupKey (that would be an
        invisible cross-group side effect through shared global
        state)."""
        source = _source()
        fn_idx = source.index("function wwActivePanelForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "ww.activePanelGroupKey =" not in fn_body


class TestWaveformGlobalYAxisZoom:
    """Waveform Y-axis zoom (owner ticket): a page-level Y Zoom In/Out
    pair, matching Event Reconstruction's own global wwErZoomYInBtn/
    wwErZoomYOutBtn (same icons, same "Zoom In/Out — Selected Y Axis"
    tooltip wording, same button order) but targeting Waveform's own
    workspace-wide wwActivePanel() (self-healing to the first available
    panel when nothing was explicitly clicked) rather than Event
    Reconstruction's own stricter "several axes, none chosen -> stay
    disabled" rule -- Waveform has exactly one Y axis per panel, never
    several in one panel, so a deterministic fallback is unambiguous."""

    def test_markup_mirrors_event_reconstructions_global_y_zoom_buttons(self):
        source = _source()
        assert 'id="wwZoomYOutBtn" title="Zoom Out — Selected Y Axis" aria-label="Zoom Out — Selected Y Axis" disabled' in source
        assert 'id="wwZoomYInBtn" title="Zoom In — Selected Y Axis" aria-label="Zoom In — Selected Y Axis" disabled' in source
        out_idx = source.index('id="wwZoomYOutBtn"')
        in_idx = source.index('id="wwZoomYInBtn"')
        assert out_idx < in_idx  # same order as Event Reconstruction's own pair

    def test_icon_keys_are_the_same_dedicated_per_axis_assets(self):
        source = _source()
        out_btn = source[source.index('id="wwZoomYOutBtn"') - 80 : source.index("</button>", source.index('id="wwZoomYOutBtn"'))]
        in_btn = source[source.index('id="wwZoomYInBtn"') - 80 : source.index("</button>", source.index('id="wwZoomYInBtn"'))]
        assert 'data-ww-icon="ZOOM_Y_OUT"' in out_btn
        assert 'data-ww-icon="ZOOM_Y_IN"' in in_btn

    def test_click_handlers_reuse_the_shared_zoom_core_against_wwactivepanel(self):
        """Not wwActivePanelForGroup(groupId) -- this pair is workspace-
        wide, resolved through the SAME self-healing wwActivePanel()
        Autoscale Y and panel-click selection already establish."""
        source = _source()
        assert 'document.getElementById("wwZoomYInBtn").addEventListener("click", () => wwStepZoomYPanel(wwActivePanel(), "in"));' in source
        assert 'document.getElementById("wwZoomYOutBtn").addEventListener("click", () => wwStepZoomYPanel(wwActivePanel(), "out"));' in source

    def test_shared_core_is_extracted_not_duplicated(self):
        """wwStepZoomYPanel(panel, direction) is the ONE place the
        Waveform-side zoom math lives -- both wwStepZoomY(groupId,
        direction) (per-Time-Group dropdown-driven) and the new global
        pair call through it, never a second Waveform-side copy of the
        factor/center/min-span calculation. (Event Reconstruction keeps
        its own separate, pre-existing analogous implementation against
        its own axis/layoutKey data model -- that one is untouched and
        out of scope here.)"""
        source = _source()
        assert source.count("function wwStepZoomYPanel(panel, direction)") == 1
        step_zoom_y = _function_body(source, "function wwStepZoomY(groupId, direction)", "\n        }\n")
        assert "wwStepZoomYPanel(wwActivePanelForGroup(groupId), direction);" in step_zoom_y
        assert "Math.max(newSpan, WW_MIN_Y_SPAN)" not in step_zoom_y

    def test_sync_function_disables_only_when_truly_no_panel_exists(self):
        """wwSyncGlobalZoomYControls() was renamed/broadened into
        wwSyncGlobalWaveformToolbar() by the Waveform top-toolbar
        migration (owner ticket) -- same Y-zoom logic, now one of
        several controls it syncs (see TestWaveformTopToolbarMigration
        for the rest)."""
        source = _source()
        fn_idx = source.index("function wwSyncGlobalWaveformToolbar()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const yZoomPanel = wwActivePanel();" in fn_body
        assert "zoomYIn.disabled = !yZoomPanel;" in fn_body
        assert "zoomYOut.disabled = !yZoomPanel;" in fn_body

    def test_sync_is_called_on_empty_state_update_and_on_active_panel_change(self):
        """Refreshed from two points so the tooltip's own axis name is
        never stale: every channel add/remove/workspace change
        (wwUpdateEmptyState()), and the moment the active panel itself
        changes (wwSetActivePanel(), e.g. clicking a different panel's
        header) -- the actual zoom action always reads wwActivePanel()
        fresh regardless, so this is a presentation-only dependency."""
        source = _source()
        empty_state_fn = source[source.index("function wwUpdateEmptyState()") : source.index("\n        }\n", source.index("function wwUpdateEmptyState()"))]
        assert "wwSyncGlobalWaveformToolbar();" in empty_state_fn
        set_active_fn = source[source.index("function wwSetActivePanel(panel)") : source.index("\n        }\n", source.index("function wwSetActivePanel(panel)"))]
        assert "wwSyncGlobalWaveformToolbar();" in set_active_fn

    def test_this_pair_is_never_hidden_only_disabled(self):
        """Panel-header tool visibility rule: Y-axis zoom is genuinely
        relevant to Waveform (unlike a page-unsupported tool), so it is
        never hidden -- only disabled when there is truly nothing to
        target."""
        source = _source()
        for btn_id in ("wwZoomYInBtn", "wwZoomYOutBtn"):
            button = source[source.index('id="' + btn_id + '"') - 80 : source.index("</button>", source.index('id="' + btn_id + '"'))]
            assert "hidden" not in button


class TestWaveformYAxisTargetReadout:
    """Waveform Y-axis target reference/readout (owner ticket): a
    compact "Y: <axis>" label beside the page-level Zoom Y In/Out
    buttons, reusing Event Reconstruction's own
    `.ww-er-active-axis-readout` class/typography/spacing and its own
    "Y: Select axis" empty-state wording verbatim -- no new CSS. ONE
    source of truth: the readout is written from the SAME `yZoomPanel`
    variable wwSyncGlobalWaveformToolbar() already resolves for Zoom Y
    and Autoscale Y, never a second/parallel target computation."""

    def test_markup_sits_beside_zoom_y_in_reusing_ers_own_class(self):
        source = _source()
        assert '<span class="ww-er-active-axis-readout" id="wwYAxisReadout">Y: Select axis</span>' in source
        zoom_y_in_idx = source.index('id="wwZoomYInBtn"')
        readout_idx = source.index('id="wwYAxisReadout"')
        sep_after_idx = source.index('<span class="ww-toolbar-sep"', zoom_y_in_idx)
        assert zoom_y_in_idx < readout_idx < sep_after_idx  # between Zoom Y In and the next separator

    def test_no_new_css_rule_was_added_for_the_readout(self):
        """The shared `.ww-er-active-axis-readout` rule (typography,
        130px max-width ellipsis, spacing) is defined exactly once and
        styles both pages' own readout elements -- never a second,
        Waveform-specific copy of this rule."""
        source = _source()
        assert source.count(".ww-er-active-axis-readout {") == 1

    def test_readout_text_is_written_from_the_same_yzoompanel_variable_zoom_y_uses(self):
        """The one-source-of-truth guarantee: this assertion locates the
        readout's own text assignment and confirms it reads `yZoomPanel`
        -- the exact variable `zoomYIn.disabled`/`autoscaleY.disabled`
        above it already use -- never a fresh wwActivePanel() call or
        any other resolver."""
        source = _source()
        fn_idx = source.index("function wwSyncGlobalWaveformToolbar()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        zoom_y_panel_idx = fn_body.index("const yZoomPanel = wwActivePanel();")
        readout_idx = fn_body.index('getElementById("wwYAxisReadout")')
        assert zoom_y_panel_idx < readout_idx  # declared before first use, same scope
        readout_block = fn_body[readout_idx - 20 : readout_idx + 300]
        assert '"Y: " + (yZoomPanel ? yZoomPanel.label : "Select axis")' in readout_block
        assert "wwActivePanel()" not in readout_block  # no second resolver call

    def test_empty_state_wording_matches_event_reconstructions_own_exactly(self):
        source = _source()
        assert '"Y: " + (yZoomPanel ? yZoomPanel.label : "Select axis")' in source
        # Event Reconstruction's own equivalent, for direct comparison.
        er_fn_idx = source.index("function wwErSyncActiveAxisReadout(entry)")
        er_fn_body = source[er_fn_idx : source.index("\n        }\n", er_fn_idx)]
        assert 'el.textContent = "Y: Select axis";' in er_fn_body

    def test_readout_title_cleared_when_disabled_set_when_targeted(self):
        """Matches wwErSyncActiveAxisReadout()'s own pattern: an empty
        `title` when nothing is targeted (nothing useful to show on
        hover), the full text as the title once a target exists (so a
        truncated label is still readable via the native tooltip)."""
        source = _source()
        fn_idx = source.index("function wwSyncGlobalWaveformToolbar()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'yAxisReadout.title = yZoomPanel ? yAxisText : "";' in fn_body

    def test_sync_is_called_from_the_same_hook_points_as_zoom_y(self):
        """No new trigger plumbing needed -- the readout is synced by
        the SAME wwSyncGlobalWaveformToolbar() calls wwUpdateEmptyState()/
        wwSetActivePanel() already make for Zoom Y/Autoscale Y, so every
        existing trigger (channel add/remove, workspace clear, active
        panel change) already keeps it fresh."""
        source = _source()
        empty_state_fn = source[source.index("function wwUpdateEmptyState()") : source.index("\n        }\n", source.index("function wwUpdateEmptyState()"))]
        assert "wwSyncGlobalWaveformToolbar();" in empty_state_fn
        set_active_fn = source[source.index("function wwSetActivePanel(panel)") : source.index("\n        }\n", source.index("function wwSetActivePanel(panel)"))]
        assert "wwSyncGlobalWaveformToolbar();" in set_active_fn


class TestWaveformToolbarSpacingAndIconsFollowup:
    """Owner ticket, follow-up to the top-toolbar migration: (1) a
    hidden feature-flagged button (#wwDetectEventBtn,
    WW_DETECT_EVENT_UI_ENABLED === false) left two `.ww-toolbar-sep`
    hairlines directly adjacent with nothing visible between them,
    doubling the gap between Time Display and Unit Mode; (2) Per-Unit
    Settings and (3) Clear Waveforms now use owner-supplied SVG assets
    through the shared registry instead of hand-drawn inline <svg>."""

    def test_detect_event_button_and_its_trailing_separator_toggle_together(self):
        source = _source()
        assert 'id="wwDetectEventSep"' in source
        assert 'document.getElementById("wwDetectEventSep").hidden = !WW_DETECT_EVENT_UI_ENABLED;' in source
        assert 'document.getElementById("wwDetectEventBtn").hidden = !WW_DETECT_EVENT_UI_ENABLED;' in source

    def test_no_two_toolbar_seps_sit_back_to_back_in_the_wwtoolbar_markup(self):
        """Structural proof the gap-doubling root cause cannot recur
        silently: between #wwToolbar's own opening tag and the
        toolbar-spacer, every `.ww-toolbar-sep` is separated from the
        next by at least one non-comment, non-whitespace markup line
        (a button or group), EXCEPT the one pair deliberately toggled
        together above."""
        source = _source()
        toolbar_idx = source.index('<div class="ww-toolbar" id="wwToolbar">')
        spacer_idx = source.index('<div class="toolbar-spacer">', toolbar_idx)
        toolbar_markup = source[toolbar_idx:spacer_idx]
        sep_positions = []
        start = 0
        while True:
            idx = toolbar_markup.find('class="ww-toolbar-sep"', start)
            if idx == -1:
                break
            sep_positions.append(idx)
            start = idx + 1
        assert len(sep_positions) >= 2
        for i in range(len(sep_positions) - 1):
            between = toolbar_markup[sep_positions[i] : sep_positions[i + 1]]
            # A real control (an id=, or a nested group div) sits between
            # this pair of separators -- i.e. they are not adjacent.
            assert "id=" in between, "two separators with nothing rendered between them at position " + str(i)

    def test_per_unit_settings_button_uses_the_registered_asset_not_inline_svg(self):
        source = _source()
        btn_idx = source.index('id="wwOpenPerUnitSettingsBtn"')
        btn = source[btn_idx - 80 : source.index("</button>", btn_idx)]
        assert 'data-ww-icon="PU_SETTINGS"' in btn
        assert "<svg" not in btn
        assert 'PU_SETTINGS: "assets/icons/waveform/pu_settings.svg"' in source
        # Handler/tooltip/accessibility/position-defining attributes
        # untouched by the icon swap.
        assert 'title="Per-Unit Settings&hellip;" aria-label="Per-Unit Settings&hellip;"' in btn

    def test_clear_waveforms_button_uses_the_registered_asset_not_inline_svg(self):
        source = _source()
        btn_idx = source.index('id="clearWorkspaceBtn"')
        btn = source[btn_idx - 40 : source.index("</button>", btn_idx)]
        assert 'data-ww-icon="CLEAR_WAVEFORMS"' in btn
        assert "<svg" not in btn
        assert 'CLEAR_WAVEFORMS: "assets/icons/waveform/clear_waveforms.svg"' in source
        assert 'title="Clear displayed waveforms" aria-label="Clear Waveforms"' in btn

    def test_clear_waveforms_moved_to_the_left_operational_group(self):
        """Was on the right side beside Edit Channel Groups/Split View;
        now sits on the left, after Annotate/Annotations, before the
        toolbar-spacer -- never inside the right-aligned view/layout
        group."""
        source = _source()
        annotations_idx = source.index('id="wwAnnotationListBtn"')
        clear_idx = source.index('id="clearWorkspaceBtn"')
        spacer_idx = source.index('<div class="toolbar-spacer">')
        split_view_idx = source.index('id="wwSplitViewBtn"')
        edit_groups_idx = source.index('id="editChannelGroupsBtn"')
        toolbar_close_idx = source.index("</div>", edit_groups_idx)
        assert annotations_idx < clear_idx < spacer_idx  # left group, before the spacer
        assert spacer_idx < split_view_idx  # right group starts only after the spacer
        # No leftover id="clearWorkspaceBtn" markup inside the right-side
        # group itself (between Split View and the toolbar's own closing
        # tag) -- scoped to the markup only, not the whole file, since an
        # unrelated JS registry comment later in the file also happens to
        # mention this id by name.
        assert 'id="clearWorkspaceBtn"' not in source[split_view_idx:toolbar_close_idx]

    def test_only_one_clear_waveforms_button_exists(self):
        source = _source()
        assert source.count('id="clearWorkspaceBtn"') == 1

    def test_clear_waveforms_handler_and_semantics_unchanged(self):
        """Same unchanged wwClearWorkspace() -- display-only, clears
        every displayed panel/channel, never the underlying source
        recording server-side. This ticket is a placement/visibility
        refinement only."""
        source = _source()
        assert 'document.getElementById("clearWorkspaceBtn").addEventListener("click", wwClearWorkspace);' in source


class TestWaveformTopToolbarMigration:
    """Waveform top-toolbar migration (owner ticket): Zoom X In/Out,
    Autoscale X, Autoscale Y and A/B Cursors move from each Time Group
    Canvas's own local toolbar to page-level #wwToolbar, alongside the
    already-global Zoom Y (DEC-156). Zoom X, Autoscale X and A/B
    Cursors share ONE "active Time Group" concept --
    wwActiveTimeGroupId(), a projection of wwActivePanel()'s own
    groupKey through wwPanelTimeGroupId(). Autoscale Y (owner
    correction) instead shares Zoom Y's own exact single-axis target --
    wwActivePanel() directly -- never "every panel in the group"; see
    TestAutoscaleYSharesZoomYsTarget below. Every click handler reuses
    an EXISTING, unchanged core function (wwStepZoomX/
    wwResetOneTimeGroupView/wwStepZoomYPanel/wwAutoscaleYPanel/
    wwToggleMeasurementCursors); only how its groupId/panel argument is
    resolved is new."""

    def test_active_time_group_id_derives_from_the_active_panel_not_new_state(self):
        source = _source()
        fn_idx = source.index("function wwActiveTimeGroupId()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const panel = wwActivePanel();" in fn_body
        assert "wwPanelTimeGroupId(panel)" in fn_body

    def test_markup_mirrors_event_reconstructions_global_x_zoom_buttons(self):
        source = _source()
        assert 'id="wwZoomXOutBtn" title="Zoom Out — Time Axis" aria-label="Zoom Out — Time Axis" disabled' in source
        assert 'id="wwZoomXInBtn" title="Zoom In — Time Axis" aria-label="Zoom In — Time Axis" disabled' in source
        out_idx = source.index('id="wwZoomXOutBtn"')
        in_idx = source.index('id="wwZoomXInBtn"')
        assert out_idx < in_idx  # same order as Zoom Y and Event Reconstruction's own pairs

    def test_autoscale_and_cursor_markup_reuses_event_reconstructions_shared_classes(self):
        source = _source()
        assert '<button type="button" class="ww-icon-btn ww-tg-reset-view-btn" id="wwAutoscaleXBtn"' in source
        assert '<button type="button" class="ww-icon-btn ww-tg-autoscale-btn" id="wwAutoscaleYBtn"' in source
        assert '<button type="button" class="ww-icon-btn ww-tg-cursor-mode-btn" id="wwCursorModeBtn"' in source

    def test_click_handlers_reuse_existing_core_functions_unchanged(self):
        """No new zoom/autoscale/cursor math anywhere -- only how each
        handler's own target argument is resolved is new. Autoscale Y
        (owner correction) resolves wwActivePanel(), the SAME target
        Zoom Y resolves -- not wwActiveTimeGroupId()."""
        source = _source()
        assert 'document.getElementById("wwZoomXInBtn").addEventListener("click", () => wwStepZoomX(wwActiveTimeGroupId(), "in"));' in source
        assert 'document.getElementById("wwZoomXOutBtn").addEventListener("click", () => wwStepZoomX(wwActiveTimeGroupId(), "out"));' in source
        assert 'document.getElementById("wwAutoscaleXBtn").addEventListener("click", () => wwResetOneTimeGroupView(wwActiveTimeGroupId()));' in source
        assert 'document.getElementById("wwAutoscaleYBtn").addEventListener("click", () => wwAutoscaleYPanel(wwActivePanel()));' in source
        assert 'document.getElementById("wwCursorModeBtn").addEventListener("click", () => wwToggleMeasurementCursors(wwActiveTimeGroupId()));' in source

    def test_sync_function_covers_every_new_control(self):
        source = _source()
        fn_idx = source.index("function wwSyncGlobalWaveformToolbar()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const groupId = wwActiveTimeGroupId();" in fn_body
        assert "const hasGroup = groupId !== null;" in fn_body
        for btn in ("wwZoomXInBtn", "wwZoomXOutBtn", "wwAutoscaleXBtn", "wwAutoscaleYBtn", "wwCursorModeBtn"):
            assert ('getElementById("' + btn + '")') in fn_body, btn

    def test_zoom_x_out_also_disables_at_this_groups_own_full_range(self):
        """Preserves the exact nuance the now-removed local Zoom Out
        split-button had (wwSyncTimeGroupZoomControls()'s own
        atFullRange check) -- not silently dropped by the migration."""
        source = _source()
        fn_idx = source.index("function wwSyncGlobalWaveformToolbar()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwBoundsEqual(groupRange, groupBounds)" in fn_body
        assert "zoomXOut.disabled = !hasGroup || atFullRange;" in fn_body
        assert "zoomXIn.disabled = !hasGroup;" in fn_body

    def test_cursor_button_aria_pressed_reflects_the_targeted_groups_own_state(self):
        source = _source()
        fn_idx = source.index("function wwSyncGlobalWaveformToolbar()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'cursorBtn.setAttribute("aria-pressed", String(hasGroup && wwTimeGroupCursorState(groupId).enabled));' in fn_body

    def test_cursor_toggle_itself_stays_single_group_scoped_never_every_group(self):
        """wwToggleMeasurementCursors(groupId) is completely unchanged by
        this ticket -- it was already, and remains, scoped to exactly
        one group's own ww.timeGroupCursorState entry."""
        source = _source()
        fn_idx = source.index("function wwToggleMeasurementCursors(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwEnsureTimeGroupCursorStateEntry(groupId)" in fn_body
        assert "wwActiveTimeGroupIds()" not in fn_body  # never loops every group

    def test_cursor_toggle_resyncs_the_global_button_itself(self):
        source = _source()
        fn_idx = source.index("function wwToggleMeasurementCursors(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert fn_body.count("wwSyncGlobalWaveformToolbar();") == 2  # both the ON and OFF branches

    def test_none_of_the_five_migrated_controls_are_ever_hidden(self):
        """Panel-header tool visibility rule: all five are genuinely
        relevant to Waveform -- only disabled when there is truly no
        Time Group to target, never hidden outright."""
        source = _source()
        for btn_id in ("wwZoomXInBtn", "wwZoomXOutBtn", "wwAutoscaleXBtn", "wwAutoscaleYBtn", "wwCursorModeBtn"):
            button = source[source.index('id="' + btn_id + '"') - 80 : source.index("</button>", source.index('id="' + btn_id + '"'))]
            assert "hidden" not in button

    def test_t0_migrated_sync_removed(self):
        """SUPERSEDED by a later Waveform toolbar refinement ticket:
        this class's own original finding (t0 and Synchronize Sources
        both stay genuinely local, out of scope for the Zoom/Autoscale/
        Cursors migration) was explicitly revisited and reversed by the
        owner -- t0 migrated to the page-level toolbar the same way
        Zoom X/Autoscale X/A-B Cursors did (same wwActiveTimeGroupId()
        targeting model), and Synchronize Sources was removed outright
        (see test_frontend_time_group_sync.py's own removal coverage).
        wwWireTimeGroupToolbar(canvasEl, groupId) itself is kept as an
        established per-canvas wiring hook, but now wires nothing --
        there is no longer any genuinely local control left for it to
        wire."""
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert ".ww-tg-t0-btn" not in fn_body
        assert ".ww-tg-sync-btn" not in fn_body
        assert "wwOpenSyncModal" not in fn_body
        assert 'id="wwT0Btn"' in source
        assert "wwHandleSetOrClearT0ClickForGroup(wwActiveTimeGroupId())" in source
        assert 'id="wwSyncBtn"' not in source


class TestAutoscaleYSharesZoomYsTarget:
    """Waveform top-toolbar migration, owner correction (same day as
    DEC-158): Zoom Y and Autoscale Y must resolve the EXACT same
    single-axis target -- wwActivePanel() -- never "every panel in the
    active Time Group." The group-wide wwAutoscaleYForGroup(groupId)
    this correction replaces is deleted outright (its only caller was
    this one button); Event Reconstruction's own, separately-owned
    wwErAutoscaleY() stays group/workspace-wide and untouched -- this
    is a deliberate Waveform-specific divergence, not a reversal of
    Event Reconstruction's own behaviour."""

    def test_group_scoped_autoscale_y_function_no_longer_exists(self):
        source = _source()
        assert "function wwAutoscaleYForGroup(" not in source

    def test_single_axis_autoscale_y_core_restores_autorange_for_one_panel(self):
        source = _source()
        fn_idx = source.index("function wwAutoscaleYPanel(panel)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "Plotly.relayout(panel.chartEl, { \"yaxis.autorange\": true });" in fn_body
        assert "for (const panel of ww.panels)" not in fn_body  # never loops every panel

    def test_autoscale_y_click_handler_resolves_wwactivepanel_directly(self):
        """Not wwActiveTimeGroupId() -- the same wwActivePanel() Zoom Y
        itself resolves, so the two controls can never disagree."""
        source = _source()
        assert 'document.getElementById("wwAutoscaleYBtn").addEventListener("click", () => wwAutoscaleYPanel(wwActivePanel()));' in source

    def test_sync_function_disables_autoscale_y_with_the_same_condition_as_zoom_y(self):
        """Target-resolution contract point 4: no valid Y-axis -> stays
        visible, disabled -- the SAME `!yZoomPanel` condition Zoom Y
        itself uses, not a group-based one."""
        source = _source()
        fn_idx = source.index("function wwSyncGlobalWaveformToolbar()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        # Autoscale Y's own disabled/title assignment sits in the SAME
        # block as Zoom Y's (both keyed off `yZoomPanel`), before the
        # group-scoped `groupId`/`hasGroup` resolution used by Zoom X/
        # Autoscale X/Cursors -- proving it shares Zoom Y's target
        # rather than the group's.
        autoscale_y_idx = fn_body.index('getElementById("wwAutoscaleYBtn")')
        group_id_idx = fn_body.index("const groupId = wwActiveTimeGroupId();")
        assert autoscale_y_idx < group_id_idx
        autoscale_y_block = fn_body[autoscale_y_idx - 20 : group_id_idx]
        assert "autoscaleY.disabled = !yZoomPanel;" in autoscale_y_block
        assert "autoscaleY.title = \"Autoscale Y — \" + ySuffix;" in autoscale_y_block

    def test_never_hidden_only_disabled(self):
        source = _source()
        button = source[source.index('id="wwAutoscaleYBtn"') - 80 : source.index("</button>", source.index('id="wwAutoscaleYBtn"'))]
        assert "hidden" not in button


class TestResetIsGroupScopedOnly:
    """Task section 10: confirm/harden Reset Time View's per-group
    semantics -- the group toolbar must use the group-specific
    implementation, never the workspace-wide reset-all."""

    def test_reset_one_time_group_view_never_loops_every_active_group(self):
        source = _source()
        fn_idx = source.index("async function wwResetOneTimeGroupView(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwDeriveTimeGroupBounds(groupId)" in fn_body
        assert "await wwApplyAndFetchGroupViewport(groupId, bounds.start, bounds.end);" in fn_body
        assert "wwActiveTimeGroupIds()" not in fn_body

    def test_global_autoscale_x_button_wired_to_the_group_specific_function(self):
        """Waveform top-toolbar migration (owner ticket): the local
        per-canvas `.ww-tg-reset-view-btn` wiring is gone from
        wwWireTimeGroupToolbar() (see TestWaveformTopToolbarMigration);
        the page-level #wwAutoscaleXBtn now calls the SAME unchanged
        wwResetOneTimeGroupView(groupId), with groupId resolved via
        wwActiveTimeGroupId() at click time instead of a fixed canvas."""
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "ww-tg-reset-view-btn" not in fn_body
        assert 'document.getElementById("wwAutoscaleXBtn").addEventListener("click", () => wwResetOneTimeGroupView(wwActiveTimeGroupId()));' in source

    def test_workspace_wide_reset_time_view_kept_only_as_a_compatibility_wrapper(self):
        """Task section 10: 'if a workspace-global helper must remain
        for compatibility, keep it as a wrapper' -- confirmed no longer
        wired to any button."""
        source = _source()
        assert "async function wwResetTimeView()" in source
        assert 'addEventListener("click", wwResetTimeView)' not in source


class TestAutoscaleIsGroupScopedOnly:
    """Task section 11 (TG-D1 era): Autoscale Y applies only to analog
    panels in the launching Time Group.

    SUPERSEDED by the owner's later, explicit correction to the
    Waveform top-toolbar migration (DEC-158): Autoscale Y must share
    Zoom Y's own exact single-axis target (wwActivePanel()), never
    "every panel in the Time Group." wwAutoscaleYForGroup(groupId) --
    this class's own original subject -- is deleted outright (its only
    caller was the page-level button this correction retargets); see
    TestAutoscaleYSharesZoomYsTarget below for the corrected coverage."""

    def test_group_scoped_autoscale_function_is_deleted(self):
        source = _source()
        assert "function wwAutoscaleYForGroup(" not in source

    def test_global_autoscale_y_button_wired_to_the_single_axis_function(self):
        """Waveform top-toolbar migration, owner correction: the local
        per-canvas `.ww-tg-autoscale-btn` wiring stays gone from
        wwWireTimeGroupToolbar(); the page-level #wwAutoscaleYBtn calls
        the SAME wwActivePanel() Zoom Y targets, via the new
        single-axis wwAutoscaleYPanel(panel)."""
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "ww-tg-autoscale-btn" not in fn_body
        assert 'document.getElementById("wwAutoscaleYBtn").addEventListener("click", () => wwAutoscaleYPanel(wwActivePanel()));' in source

    def test_workspace_wide_autoscale_y_kept_only_as_a_compatibility_wrapper(self):
        source = _source()
        assert "function wwAutoscaleY()" in source
        assert 'addEventListener("click", wwAutoscaleY)' not in source


class TestToolbarWiringResolvesControlsFromTheLaunchingCanvas:
    """Task section 6: avoid document.getElementById() for per-group
    controls -- prefer scoped canvasEl.querySelector(), a reusable
    wiring helper receiving groupId. No manual per-group duplication."""

    def test_wire_time_group_toolbar_never_uses_document_get_element_by_id(self):
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n\n", fn_idx)]
        assert "document.getElementById(" not in fn_body

    def test_zoom_split_button_wiring_is_removed_not_merely_pointed_at_nothing(self):
        """Waveform top-toolbar migration (owner ticket): the per-canvas
        Zoom In/Out split-button wiring loop (main-button dispatch, the
        X/Y axis-choice dropdown, open/close/focus handling) is removed
        from wwWireTimeGroupToolbar() entirely -- not left querying a
        selector that no longer matches anything. wwPerformZoomStep()/
        wwSetZoomStepAxis() (their only callers) are deleted along with
        it; see TestWaveformTopToolbarMigration for the page-level
        replacement (wwZoomXInBtn/wwZoomXOutBtn calling wwStepZoomX()
        directly, no axis-choice dropdown needed any more since X and Y
        each have their own dedicated button)."""
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n\n", fn_idx)]
        assert "ww-tg-zoom-in-split" not in fn_body
        assert "ww-tg-zoom-out-split" not in fn_body
        assert "wwPerformZoomStep" not in fn_body
        assert "function wwPerformZoomStep(" not in source
        assert "function wwSetZoomStepAxis(" not in source

    def test_created_exactly_once_per_canvas_not_a_document_wide_singleton_wire_up(self):
        """The former wwWireZoomStepSplitButtons() wired two singleton
        ids ONCE at page load; wwWireTimeGroupToolbar() must instead be
        callable once per canvas, with zero references to a single
        global wiring entry point remaining."""
        source = _source()
        assert "function wwWireZoomStepSplitButtons(" not in source


class TestPerGroupZoomAxisPreferenceIsolated:
    """Case isolation for the split-button's own remembered X/Y
    preference -- choosing Y in Group 2's menu must never affect Group
    1's own remembered axis or button label.

    Waveform top-toolbar migration (owner ticket): the WRITER of this
    preference (wwSetZoomStepAxis(), the split-button dropdown's own
    click handler) is deleted along with the dropdown markup itself --
    Zoom X and Zoom Y are each their own dedicated page-level button
    now, so there is no "which axis did this group last choose" to
    remember any more. wwZoomStepAxisForGroup()/ww.zoomStepAxisByGroup
    themselves are deliberately KEPT (not deleted) because
    wwSyncTimeGroupZoomControls() -- itself still called from unrelated
    per-group viewport/bounds-sync call sites, now a harmless no-op
    since the local split-buttons it used to update no longer exist in
    the DOM -- still reads through them; removing the Map/getter would
    mean also touching that still-live function and the shared
    topology-pruning loop below, outside this ticket's own "reuse
    existing, avoid large refactors" scope. In practice every group now
    always reads back the "x"/"x" default, since nothing writes to the
    Map any more."""

    def test_zoom_step_axis_state_is_a_per_group_map(self):
        source = _source()
        assert "zoomStepAxisByGroup: new Map()" in source

    def test_axis_resolver_defaults_to_x_for_an_unset_group(self):
        source = _source()
        fn_idx = source.index("function wwZoomStepAxisForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'ww.zoomStepAxisByGroup.get(groupId) || { in: "x", out: "x" }' in fn_body

    def test_the_only_former_writer_is_removed(self):
        source = _source()
        assert "function wwSetZoomStepAxis(" not in source
        assert "ww.zoomStepAxisByGroup.set(" not in source

    def test_zoom_step_axis_map_cleared_on_workspace_clear(self):
        source = _source()
        fn_idx = source.index("function wwClearWorkspace(options)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "ww.zoomStepAxisByGroup.clear();" in fn_body

    def test_zoom_step_axis_map_pruned_when_a_groups_canvas_is_pruned(self):
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupCanvases()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "ww.zoomStepAxisByGroup.delete(groupId);" in fn_body


class TestSyncTimeGroupZoomControlsIsGroupScoped:
    """The per-group generalization of the original
    wwSyncZoomStepControls() -- tooltip/checkmark/disabled-state sync
    scoped to ONE canvas via wwTimeGroupCanvasEl(groupId), never a
    document-wide singleton lookup."""

    def test_resolves_canvas_scoped_to_this_group(self):
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupZoomControls(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const canvasEl = wwTimeGroupCanvasEl(groupId);" in fn_body
        assert "document.getElementById(" not in fn_body

    def test_zoom_out_disabled_state_reads_this_groups_own_bounds(self):
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupZoomControls(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwTimeGroupVisibleRange(groupId)" in fn_body
        assert "wwDeriveTimeGroupBounds(groupId)" in fn_body

    def test_batch_sync_loops_every_active_group(self):
        source = _source()
        fn_idx = source.index("function wwSyncAllTimeGroupZoomControls()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "for (const groupId of wwActiveTimeGroupIds()) wwSyncTimeGroupZoomControls(groupId);" in fn_body


class TestSliderRulerDigitalZoomStayTogetherAfterAnyGroupViewportChange:
    """Task section 16/17: after any X zoom/reset action, viewport <->
    slider <-> ruler <-> digital must remain synchronized for that
    group -- all four sync calls must live in the SAME unconditional
    (not primary-gated) section of wwApplyAndFetchGroupViewport().
    TG-H: peak-annotation recalculation joined this same unconditional
    group (previously primary-gated -- see
    test_frontend_time_group_annotations.py's own Case F coverage)."""

    def test_ruler_digital_slider_and_zoom_controls_all_resync_unconditionally(self):
        source = _source()
        fn_idx = source.index("async function wwApplyAndFetchGroupViewport(groupId, startTime, endTime)")
        fn_body = source[fn_idx : source.index("async function wwApplyAndFetchViewport(startTime, endTime)", fn_idx)]
        primary_idx = fn_body.index("if (isPrimary) {")
        primary_end = fn_body.index("ww.viewport = { start: startTime, end: endTime };", primary_idx) + len(
            "ww.viewport = { start: startTime, end: endTime };"
        )
        unconditional_tail = fn_body[primary_end:]
        assert "wwRecalculateAllPeakAnnotations(groupId, startTime, endTime);" in unconditional_tail
        assert "wwSyncTimeGroupRuler(groupId);" in unconditional_tail
        assert "wwRebuildDigitalChart(groupId);" in unconditional_tail
        assert "wwSyncTimeGroupSliderForCanvas(groupId, canvasEl);" in unconditional_tail
        assert "wwSyncTimeGroupZoomControls(groupId);" in unconditional_tail

    def test_panel_relayout_restricted_to_this_groups_own_panels(self):
        source = _source()
        fn_idx = source.index("async function wwApplyAndFetchGroupViewport(groupId, startTime, endTime)")
        fn_body = source[fn_idx : source.index("async function wwApplyAndFetchViewport(startTime, endTime)", fn_idx)]
        assert "if (wwPanelTimeGroupId(panel) !== groupId) continue;" in fn_body

    def test_refetch_restricted_to_this_groups_own_channels(self):
        source = _source()
        fn_idx = source.index("async function wwApplyAndFetchGroupViewport(groupId, startTime, endTime)")
        fn_body = source[fn_idx : source.index("async function wwApplyAndFetchViewport(startTime, endTime)", fn_idx)]
        assert "await wwRefetchChannelsForGroup(groupId, startTime, endTime);" in fn_body


class TestDoubleClickAutorangeGestureIsGroupScoped:
    """Plotly's own native double-click-to-autorange gesture on a panel
    is a Reset action too -- must reset only that panel's own Time
    Group, matching the isolation rule for every other Reset path."""

    def test_autorange_gesture_resets_only_the_panels_own_group(self):
        source = _source()
        fn_idx = source.index("function wwWirePanelRelayout(panel)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwResetOneTimeGroupView(wwPanelTimeGroupId(panel));" in fn_body
        assert "wwResetTimeView();" not in fn_body


class TestLayoutModePreservesLocalToolbarOwnership:
    """Task section K / TG-D1's own non-goal list: Layout Mode stays
    workspace-global, but a layout-mode switch must never destroy or
    duplicate a canvas's own local toolbar -- wwRebuildLayout() only
    ever clears each canvas's own `.ww-tg-panels`, never the canvas
    root (and therefore never its toolbar) itself."""

    def test_rebuild_layout_only_clears_the_panels_container_never_the_toolbar(self):
        source = _source()
        fn_idx = source.index("function wwRebuildLayout()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'canvasEl.querySelector(".ww-tg-panels")' in fn_body
        assert "ww-tg-toolbar" not in fn_body
        assert "wwCreateTimeGroupCanvasDom" not in fn_body


class TestGlobalDuplicatesRemoved:
    """Task section 12: after migration, the original workspace-global
    toolbar must not retain a duplicate, still-active way to invoke any
    of the four migrated controls."""

    def test_no_global_zoom_split_button_markup_remains(self):
        source = _source()
        for stale_id in ("wwZoomInSplit", "wwZoomOutSplit", "wwZoomInBtn", "wwZoomOutBtn", "wwZoomInMenu", "wwZoomOutMenu"):
            assert f'id="{stale_id}"' not in source, f"stale global zoom markup id={stale_id} still present"

    def test_no_global_reset_or_autoscale_button_markup_remains(self):
        source = _source()
        assert 'id="wwResetViewBtn"' not in source
        assert 'id="wwAutoscaleBtn"' not in source

    def test_no_global_wiring_call_for_the_old_singleton_split_buttons(self):
        source = _source()
        assert "wwWireZoomStepSplitButtons();" not in source

    def test_deferred_global_controls_are_still_present_and_untouched(self):
        """Task section 4/12: Layout Mode, Time Mode, Unit Mode,
        Synchronise Sources, upload, and the annotation drawer all
        remain workspace-global -- confirms this slice did not
        accidentally remove or migrate them. (Cursor A/B was migrated in
        the later TG-D2 slice, and t0 in the later TG-E slice -- see
        test_frontend_time_group_cursors.py/test_frontend_synchronization_t0.py
        for their own coverage.)"""
        source = _source()
        for still_global_id in (
            "layoutModeGroupedBtn",
            "timeModeAbsoluteBtn",
            "wwUnitEngineeringBtn",
            "recordingsUploadBtn",
        ):
            assert f'id="{still_global_id}"' in source, f"expected still-global control id={still_global_id} to remain"


class TestMergeSplitLifecycleAlwaysProducesAToolbar:
    """Task section 18/Case L: toolbar count follows active Time Group
    count. Since every Time Group Canvas -- however it comes to exist,
    whether from a genuinely new group, a merge, or a split -- is only
    ever created through the ONE wwCreateTimeGroupCanvasDom() template
    (which always includes the toolbar and always wires it), there is
    no code path that can produce a canvas without a local toolbar, and
    no separate/duplicate creation path that could double-wire one."""

    def test_only_one_function_builds_a_time_group_canvas_root(self):
        source = _source()
        assert source.count("section.className = \"ww-time-group-canvas\";") == 1

    def test_canvas_creating_helper_has_no_new_unaudited_call_sites(self):
        source = _source()
        # "= wwEnsureTimeGroupCanvasDom(groupId)" matches every CALL site
        # (an assignment/ternary result) but not the function's own
        # `function wwEnsureTimeGroupCanvasDom(groupId) {` signature.
        count = source.count("wwEnsureTimeGroupCanvasDom(groupId)") - 1
        assert count == 4, (
            "A new, unaudited call site to the CREATING "
            "wwEnsureTimeGroupCanvasDom() was added this slice -- every "
            "canvas (and therefore every toolbar) must still only ever "
            "come from the same four already-audited creators."
        )
