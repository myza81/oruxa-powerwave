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


def test_ww_state_has_unit_mode_and_per_unit_source_configs():
    source = _source()
    body = _function_body(source, "const ww = {", "function wwFiniteNumber(value)")
    assert 'unitMode: "engineering"' in body
    assert "perUnitSourceConfigs: new Map()" in body


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
    # A workspace with an already-configured source from an earlier
    # session must not be mistaken for "none yet" by the auto-open check
    # -- source configs are fetched BEFORE ww.unitMode itself flips.
    assert body.index("await wwFetchPerUnitSourceConfigs()") < body.index("ww.unitMode = mode;")


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


def test_start_new_workspace_resets_unit_mode_and_source_configs_plain_clear_does_not():
    source = _source()
    body = _function_body(source, "function wwClearWorkspace(options)", "function wwStickyRulerElapsedUnit(spanSeconds)")
    reset_branch = body[body.index("if (options.resetSourceBounds)") : body.index("} else {")]
    else_branch = body[body.index("} else {") :]
    assert 'ww.unitMode = "engineering";' in reset_branch
    assert "ww.perUnitSourceConfigs.clear();" in reset_branch
    assert "wwClosePerUnitProfilesModal();" in reset_branch
    assert 'ww.unitMode = "engineering"' not in else_branch
    assert "ww.perUnitSourceConfigs.clear()" not in else_branch


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


def test_every_loaded_source_appears_automatically_via_the_existing_source_list():
    """Section 1: reuses fetchSourcesList()/recordingDisplayName() --
    the SAME source-listing/label convention as the Recordings page and
    Workspace Sidebar -- never a second "what is this file called"
    mechanism, and never the filename as any kind of persistent
    identity (source_id is)."""
    source = _source()
    body = _function_body(source, "async function wwOpenPerUnitProfilesModal()", "function wwClosePerUnitProfilesModal()")
    assert "await fetchSourcesList();" in body
    assert "await wwFetchPerUnitSourceConfigs();" in body

    select_body = _function_body(source, "function wwRenderPerUnitSourceSelect()", "function wwPerUnitSourceSelectChange(")
    assert "recordingDisplayName(source)" in select_body
    assert "source.source_id" in select_body


def test_source_config_save_targets_the_source_scoped_endpoint():
    source = _source()
    body = _function_body(source, "async function wwApplyPerUnitProfileEditor()", "async function wwDeletePerUnitProfileEditor()")
    assert '"/per-unit/sources/" + encodeURIComponent(state.sourceId)' in body
    assert '"PUT"' in body
    assert "voltage_reference_mode: state.voltageReferenceMode" in body
    assert "voltage_reference_override: state.voltageReferenceMode === \"manual\" ? state.voltageReferenceOverride : null" in body


def test_voltage_reference_block_covers_auto_manual_and_ambiguous_states():
    """Section 6-8: three distinct renderings -- confident auto-
    detection with an Override action, an active manual override with a
    Return-to-Auto action, and an honest "could not determine" fallback
    -- never a silently invented default."""
    source = _source()
    body = _function_body(source, "function wwRenderVoltageReferenceBlock(state)", "function wwWirePerUnitProfileFieldsEvents()")
    assert 'state.voltageReferenceMode === "manual"' in body
    assert "Return to Auto" in body
    assert "state.autoDetection.reference" in body
    assert "Override" in body
    assert "Could not determine automatically" in body
    assert "perUnitVoltageReferenceFallback" in body


def test_return_to_auto_reruns_rather_than_keeps_the_stale_manual_choice():
    source = _source()
    body = _function_body(source, "function wwWirePerUnitProfileFieldsEvents()", "function wwRenderPerUnitProfileEditor()")
    return_section = body[body.index("perUnitReturnToAutoBtn") :]
    assert 'state.voltageReferenceMode = "auto";' in return_section
    assert "state.voltageReferenceOverride = null;" in return_section


def test_voltage_base_field_uses_a_fixed_suffix_not_a_unit_dropdown():
    """Section 4: a wide numeric field plus a non-editable unit suffix
    -- the domain always accepts one canonical unit (kV) for this field,
    so no dropdown is offered."""
    source = _source()
    body = _function_body(source, "function wwRenderPerUnitProfileEditor()", "async function wwApplyPerUnitProfileEditor()")
    assert 'class="ww-pu-value-suffix-group"' in body
    assert '<span class="ww-pu-suffix">kV</span>' in body
    assert "perUnitVoltageBaseUnit" not in body  # no unit <select> any more


def test_current_base_uses_three_labeled_radio_options():
    source = _source()
    body = _function_body(source, "function wwRenderPerUnitProfileEditor()", "async function wwApplyPerUnitProfileEditor()")
    assert "Calculate from apparent power" in body
    assert "Enter current base manually" in body
    assert "Voltage only" in body
    assert 'name="perUnitCurrentBaseMode"' in body


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
    assert 'id="perUnitSourceSelect"' in source


def test_first_switch_to_per_unit_with_no_configured_source_auto_opens_setup_modal():
    source = _source()
    start = source.index('.ww-split-menu-item[data-unit-mode="per_unit"]\').addEventListener("click"')
    end = source.index("});", start) + 3
    body = source[start:end]
    assert "await wwApplyUnitMode(\"per_unit\");" in body
    assert "some((c) => c.configured)" in body
    assert "await wwOpenPerUnitProfilesModal();" in body
