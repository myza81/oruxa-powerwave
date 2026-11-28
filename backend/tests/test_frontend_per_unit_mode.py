"""Static regression checks for the Phase 5C Global Per-Unit Measurement
Mode frontend (DEC-049; source-bound redesign following owner UAT) --
same source-text substring-assertion pattern as
test_frontend_calculated_channel_time_mode.py: this repo has no
browser/DOM test runner for the single-file frontend, so key invariants
are locked in as literal-source assertions plus direct Playwright
verification (see the Phase 5C-UAT implementation report).
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


def test_ww_state_has_unit_mode_no_per_unit_source_configs():
    """PU-UI-001 Step B: `perUnitSourceConfigs` state was removed with the
    SD modal.  `unitMode` remains -- it is a waveform display toggle, not
    a modal-scoped field."""
    source = _source()
    body = _function_body(source, "const ww = {", "function wwFiniteNumber(value)")
    assert 'unitMode: "engineering"' in body
    assert "perUnitSourceConfigs: new Map()" not in body


def test_every_channel_waveform_fetch_requests_unit_mode():
    """Slice 3A (DEC-127): the request itself is built by the shared
    fetch core; Waveform's wrapper passes its own ww.unitMode.
    DEC-212: raw Current channels always pass "engineering" regardless of
    the toggle -- the wrapper applies the guard before calling the core."""
    source = _source()
    wrapper = _function_body(
        source, "async function wwFetchChannelRange(channelEntry", "async function wwFetchWaveformRange(request)"
    )
    # DEC-212: Current channels always use engineering; other channels use ww.unitMode.
    assert 'channelEntry.engineeringType === "Current" ? "engineering" : ww.unitMode' in wrapper
    core = _function_body(source, "async function wwFetchWaveformRange(request)", "function wwFriendlyError(code, message)")
    assert 'url.searchParams.set("unit_mode", unitMode);' in core


def test_apply_unit_mode_refetches_and_regroups():
    """Time Range slider: a unit-mode switch is a workspace-wide trigger,
    not itself a viewport change, so it now refetches every displayed
    channel using ITS OWN Time Group's current viewport
    (wwRefetchAllChannelsAcrossGroups()) rather than one shared range --
    in the common single-Time-Group workspace this is the exact same
    request as before.

    PU-UI-001 Step B: `void wwFetchPerUnitSourceConfigs()` was removed
    with the SD modal; `wwApplyUnitMode` no longer calls it.
    """
    source = _source()
    body = _function_body(source, "async function wwApplyUnitMode(mode)", "function wwSyncUnitModeControls()")
    assert "if (ww.unitMode === mode) return;" in body
    assert "ww.unitMode = mode;" in body
    assert "await wwRefreshWaveformDisplayBasis();" in body
    refresh = _function_body(source, "async function wwRefreshWaveformDisplayBasis(", "\n        // RD-1 Slice B (D2 decision)")
    assert "await wwRefetchAllChannelsAcrossGroups(sourceIds);" in refresh
    assert "wwRebuildLayout();" in refresh
    assert "wwUpdateUnitModeWarningBadge();" in refresh
    assert "modeGeneration !== wwUnitModeGeneration" in refresh
    # PU-UI-001 Step B: SD modal fetch no longer called on mode change.
    assert "void wwFetchPerUnitSourceConfigs()" not in body


def test_panel_group_key_never_mixes_configured_and_base_required():
    source = _source()
    body = _function_body(source, "function wwPanelGroupKeyFor(", "function wwPanelLabelFor(channel)")
    # Separate/Custom modes return early -- the per-unit branch below is
    # reached only in Grouped mode (one channel-per-panel already can't
    # mix anything in Separate; Custom groups are explicit, user-owned).
    assert 'layoutMode = ww.layoutMode' in body
    assert body.index('layoutMode === "separate"') < body.index('ww.unitMode === "per_unit"')
    assert body.index('layoutMode === "custom"') < body.index('ww.unitMode === "per_unit"')
    assert 'return baseKey + ":pu";' in body
    assert 'return baseKey + ":base_required";' in body


def test_panel_label_matches_group_key_suffixes():
    source = _source()
    body = _function_body(source, "function wwPanelLabelFor(channel)", "function wwNextColor()")
    assert 'return baseLabel + " (pu)";' in body
    assert 'return baseLabel + " (Base required)";' in body


def test_start_new_workspace_resets_unit_mode_plain_clear_does_not():
    """PU-UI-001 Step B: `perUnitSourceConfigs.clear()` and
    `wwClosePerUnitProfilesModal()` were removed with the SD modal.
    `ww.unitMode = "engineering"` reset still fires on resetSourceBounds."""
    source = _source()
    body = _function_body(source, "function wwClearWorkspace(options)", "function wwStickyRulerElapsedUnit(spanSeconds)")
    reset_branch = body[body.index("if (options.resetSourceBounds)") : body.index("} else {")]
    else_branch = body[body.index("} else {") :]
    assert 'ww.unitMode = "engineering";' in reset_branch
    assert "ww.perUnitSourceConfigs.clear();" not in reset_branch
    assert "wwClosePerUnitProfilesModal();" not in reset_branch
    assert 'ww.unitMode = "engineering"' not in else_branch


def test_no_separate_profile_concept_remains_in_the_user_facing_workflow():
    """Section 1: the engineer never creates/names/selects a "profile"
    or manually assigns an ordinary channel to one -- the old
    assignment-conflict machinery (channel_already_assigned, a channel
    checklist, "Move here") is fully retired."""
    source = _source()
    assert "channel_already_assigned" not in source
    assert "assignedChannelKeys" not in source
    assert "ww-per-unit-move-btn" not in source
    assert "perUnitChannelChecklist" not in source
    assert "perUnitNameInput" not in source


def test_sd_modal_removed_in_pu_ui_001():
    """PU-UI-001 Step B: the entire SD modal surface and its functions
    were removed.  Recording Details is now the sole per-unit config
    entry point.  These assertions form the new regression contract for
    all the per-source-default tests that previously appeared here."""
    source = _source()
    # Modal markup is gone.
    assert 'id="perUnitProfilesOverlay"' not in source
    assert 'id="perUnitSourceSelect"' not in source
    # Open/close functions are gone.
    assert 'async function wwOpenPerUnitProfilesModal(' not in source
    assert 'function wwClosePerUnitProfilesModal()' not in source
    # SD editor render/wire/apply/delete functions are gone.
    assert 'function wwRenderPerUnitProfileEditor(' not in source
    assert 'function wwRenderVoltageReferenceBlock(' not in source
    assert 'function wwWirePerUnitProfileFieldsEvents()' not in source
    assert 'async function wwApplyPerUnitProfileEditor()' not in source
    assert 'async function wwDeletePerUnitProfileEditor()' not in source
    # SD state functions are gone.
    assert 'function wwPerUnitConfigToEditorState(' not in source
    assert 'function wwFetchPerUnitSourceConfigs' not in source
    assert 'function wwRenderPerUnitSourceSelect()' not in source
    assert 'function wwRenderPerUnitSourceStatusLine()' not in source
    # SD API path strings are gone.
    assert '"/per-unit/sources"' not in source
    assert '"/per-unit/sources/"' not in source
    # RD navigation helpers have replaced the modal entry points.
    assert 'function wwNavigateToRdForPuConfiguration(' in source


def test_cursor_peak_and_annotation_anchor_requests_all_carry_unit_mode():
    source = _source()
    body = _function_body(
        source, "async function wwFetchCursorValuesForSource(sourceId)", "function wwFetchAllCursorValuesForGroup(groupId)"
    )
    # DEC-212 (Slice 6C): cursor routes per engineering-type.
    # Calculated path sends unit_mode: ww.unitMode directly.
    # Non-calculated path uses batchUnitMode (= ww.unitMode snapshot for non-Current,
    # "engineering" for Current) — both shapes carry unit_mode.
    assert body.count("unit_mode: ww.unitMode") >= 1  # calculated path
    assert "unit_mode: batchUnitMode" in body  # non-calculated path routing

    full_source = source
    # DEC-212 (Slice 6C.1): non-calculated raw Current paths in callout/peak/anchor now use
    # "engineering" conditional instead of ww.unitMode directly.  Calculated-channel paths
    # (and ER cursor) still use ww.unitMode — check both forms are present.
    assert full_source.count("unit_mode: ww.unitMode") >= 3  # calculated-channel paths
    assert full_source.count('"engineering" : ww.unitMode') >= 3  # DEC-212 raw Current conditional


def test_calculated_channel_preview_uses_the_same_global_unit_mode():
    source = _source()
    body = _function_body(
        source, "async function wwCcFetchPreviewWaveform(calc)", "function wwCcPreviewPurgeAllPanels()"
    )
    assert 'encodeURIComponent(ww.unitMode)' in body


def test_manage_per_unit_bases_toolbar_control_exists_in_html():
    """PU-UI-001 Step B: Hub and SD modal are both removed.  Only the
    ENG/PU toggle buttons remain in Voltage pane headers for display switching;
    all PU configuration goes through Recording Details."""
    source = _source()
    # Pane-header relocation: native ENG/PU buttons, one workspace-wide state.
    assert 'data-pane-unit-mode="engineering"' in source
    assert 'data-pane-unit-mode="per_unit"' in source
    # Hub and SD modal are gone.
    assert 'id="wwOpenPerUnitSettingsBtn"' not in source
    assert 'id="perUnitProfilesOverlay"' not in source
    assert 'id="perUnitSourceSelect"' not in source


def test_selecting_per_unit_never_auto_opens_any_configuration_surface():
    """Slice 1 UAT fix (Per-Unit Settings hierarchy): selecting Per Unit
    used to auto-open the source-wide setup modal.  That side effect is
    removed outright -- opening any configuration surface must always be
    a separate, explicit action via Recording Details, never a consequence
    of switching display mode.

    PU-UI-001 Step B: SD modal and MG modal are both gone; this remains
    a valid regression contract (the Per Unit click must ONLY change
    display mode, nothing else)."""
    source = _source()
    start = source.index('async function wwApplyPaneUnitMode(panel, button)')
    end = source.index("function wwWaveformPaneHeaderHtml", start)
    body = source[start:end]
    assert "wwApplyUnitMode(button.dataset.paneUnitMode)" in body
    assert "wwOpenPerUnitProfilesModal" not in body
    assert "wwOpenPerUnitSettingsModal" not in body
    assert "wwOpenMeasurementGroupsModal" not in body
    assert "some((c) => c.configured)" not in body
