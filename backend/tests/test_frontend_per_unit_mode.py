"""Static regression checks for the Phase 5C Global Per-Unit Measurement
Mode frontend (DEC-049) -- same source-text substring-assertion pattern
as test_frontend_calculated_channel_time_mode.py: this repo has no
browser/DOM test runner for the single-file frontend, so key invariants
are locked in as literal-source assertions plus direct Playwright
verification (see the Phase 5C implementation report).
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


def test_ww_state_has_unit_mode_and_per_unit_profiles():
    source = _source()
    body = _function_body(source, "const ww = {", "function wwFiniteNumber(value)")
    assert 'unitMode: "engineering"' in body
    assert "perUnitProfiles: new Map()" in body


def test_every_channel_waveform_fetch_requests_unit_mode():
    source = _source()
    body = _function_body(
        source, "async function wwFetchChannelRange(channelEntry", "function wwFriendlyError(code, message)"
    )
    assert 'url.searchParams.set("unit_mode", ww.unitMode)' in body


def test_apply_unit_mode_refetches_and_regroups():
    source = _source()
    body = _function_body(source, "async function wwApplyUnitMode(mode)", "function wwSyncUnitModeControls()")
    assert "if (ww.unitMode === mode) return;" in body
    assert "ww.unitMode = mode;" in body
    assert "await wwRefetchAllChannels(startTime, endTime);" in body
    assert "wwRebuildLayout();" in body
    assert "wwUpdateUnitModeWarningBadge();" in body
    # Decision: a workspace with existing profiles from an earlier
    # session must not be mistaken for "none yet" by the auto-open
    # check -- profiles are fetched BEFORE ww.unitMode itself flips.
    assert body.index("await wwFetchPerUnitProfiles()") < body.index("ww.unitMode = mode;")


def test_panel_group_key_never_mixes_configured_and_base_required():
    source = _source()
    body = _function_body(source, "function wwPanelGroupKeyFor(channel)", "function wwPanelLabelFor(channel)")
    # Separate/Custom modes return early -- the per-unit branch below is
    # reached only in Grouped mode (one channel-per-panel already can't
    # mix anything in Separate; Custom groups are explicit, user-owned).
    assert body.index('ww.layoutMode === "separate"') < body.index('ww.unitMode === "per_unit"')
    assert body.index('ww.layoutMode === "custom"') < body.index('ww.unitMode === "per_unit"')
    assert 'return baseKey + ":pu";' in body
    assert 'return baseKey + ":base_required";' in body


def test_panel_label_matches_group_key_suffixes():
    source = _source()
    body = _function_body(source, "function wwPanelLabelFor(channel)", "function wwNextColor()")
    assert 'return baseLabel + " (pu)";' in body
    assert 'return baseLabel + " (Base required)";' in body


def test_start_new_workspace_resets_unit_mode_and_profiles_plain_clear_does_not():
    source = _source()
    body = _function_body(source, "function wwClearWorkspace(options)", "function wwStickyRulerElapsedUnit(spanSeconds)")
    reset_branch = body[body.index("if (options.resetSourceBounds)") : body.index("} else {")]
    else_branch = body[body.index("} else {") :]
    assert 'ww.unitMode = "engineering";' in reset_branch
    assert "ww.perUnitProfiles.clear();" in reset_branch
    assert "wwClosePerUnitProfilesModal();" in reset_branch
    assert 'ww.unitMode = "engineering"' not in else_branch
    assert "ww.perUnitProfiles.clear()" not in else_branch


def test_channel_already_assigned_requires_explicit_confirmation_before_reassigning():
    source = _source()
    body = _function_body(
        source, "async function wwApplyPerUnitProfileEditor(reassignConflicting)", "async function wwDeletePerUnitProfileEditor()"
    )
    assert '"channel_already_assigned"' in body
    assert "window.confirm(" in body
    assert "body.reassign_conflicting = !!reassignConflicting;" in body
    # The FIRST attempt is always sent without forcing reassignment --
    # only a confirmed retry sets it true.
    assert body.index("body.reassign_conflicting = !!reassignConflicting;") < body.index('detail.code === "channel_already_assigned"')


def test_owned_elsewhere_checkbox_is_disabled_until_explicit_move_action():
    source = _source()
    body = _function_body(
        source, "function wwPerUnitChannelChecklistItemHtml(key, label)", "function wwRenderPerUnitChannelChecklist()"
    )
    assert "const showMoveAction = !!owner && !checked;" in body
    assert "ww-per-unit-move-btn" in body
    # A checkbox can never be BOTH checked and disabled by construction
    # here -- disabled is conditioned on `!checked`.
    assert "(showMoveAction ? \" disabled\" : \"\")" in body


def test_move_here_action_adds_channel_to_working_copy_not_the_backend_directly():
    source = _source()
    body = _function_body(
        source, "function wwRenderPerUnitChannelChecklist()", "function wwRenderPerUnitProfileEditor()"
    )
    assert "perUnitEditorState.assignedChannelKeys.add(btn.dataset.channelKey);" in body
    assert "wwRenderPerUnitChannelChecklist(); // re-render" in body


def test_cursor_peak_and_annotation_anchor_requests_all_carry_unit_mode():
    source = _source()
    body = _function_body(
        source, "async function wwFetchCursorValuesForSource(sourceId)", "function wwFetchAllCursorValues()"
    )
    assert body.count("unit_mode: ww.unitMode") >= 2  # both the calculated and source-channel request shapes

    full_source = source
    # Peak-values: both the interactive-creation and the recalculation-
    # on-viewport-change call sites.
    assert full_source.count("unit_mode: ww.unitMode") >= 6


def test_calculated_channel_preview_uses_the_same_global_unit_mode():
    source = _source()
    body = _function_body(
        source, "async function wwCcFetchPreviewWaveform(calc)", "function wwCcPreviewPurgeAllPanels()"
    )
    assert 'encodeURIComponent(ww.unitMode)' in body


def test_manage_per_unit_bases_toolbar_control_exists_in_html():
    source = _source()
    assert 'id="wwUnitModeBtn"' in source
    assert 'id="wwUnitModeMenu"' in source
    assert 'data-unit-mode="engineering"' in source
    assert 'data-unit-mode="per_unit"' in source
    assert 'id="wwManagePerUnitBasesBtn"' in source
    assert 'id="perUnitProfilesOverlay"' in source


def test_first_switch_to_per_unit_with_zero_profiles_auto_opens_setup_modal():
    source = _source()
    start = source.index('.ww-split-menu-item[data-unit-mode="per_unit"]\').addEventListener("click"')
    end = source.index("});", start) + 3
    body = source[start:end]
    assert "await wwApplyUnitMode(\"per_unit\");" in body
    assert "ww.perUnitProfiles.size === 0" in body
    assert "await wwOpenPerUnitProfilesModal();" in body
