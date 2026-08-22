"""Static regression checks for the RMS Calculated Channel UI (Phase 5B,
DEC-048). Same source-text substring-assertion pattern as
test_frontend_calculated_channel_time_mode.py -- this repo has no
browser/DOM test runner for the single-file frontend.
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


def test_rms_operation_is_registered():
    source = _source()
    assert '"reverse_polarity", "absolute_value", "multiply_constant", "rms", "addition", "subtraction"' in source
    ops_body = _function_body(source, "const WW_CC_OPERATIONS = {", "const WW_CC_OPERATION_ORDER")
    assert 'rms: {' in ops_body
    assert '"1-cycle true RMS"' in ops_body or "1-cycle true RMS" in ops_body


def test_builder_state_has_rms_fields():
    source = _source()
    body = _function_body(source, "const wwCcBuilder = {", "const wwCcListErrors")
    assert "nominalFrequency: \"50\"" in body
    assert "override: false" in body


def test_reset_builder_resets_rms_fields():
    source = _source()
    body = _function_body(source, "function wwCcResetBuilder()", "function wwCcResetRmsEligibility()")
    assert 'wwCcBuilder.nominalFrequency = "50";' in body
    assert "wwCcBuilder.override = false;" in body
    assert "wwCcResetRmsEligibility();" in body


def test_suggested_name_has_rms_branch():
    source = _source()
    body = _function_body(source, "function wwCcComputeSuggestedName()", "function wwCcComputeExpressionPreview()")
    assert '"RMS(" + labels[0] + ")"' in body


def test_expression_preview_has_rms_branch():
    source = _source()
    body = _function_body(source, "function wwCcComputeExpressionPreview()", "function wwCcValidateBuilder()")
    assert 'b.operation === "rms"' in body
    assert "Hz, 1 cycle" in body


def test_operation_summary_text_has_rms_branch():
    source = _source()
    body = _function_body(source, "function wwCcOperationSummaryText(calc)", "function wwCcComputeSuggestedName()")
    assert 'calc.operation === "rms"' in body
    assert "nominal_frequency_hz" in body


def test_validate_builder_checks_nominal_frequency():
    source = _source()
    body = _function_body(source, "function wwCcValidateBuilder()", "function wwCcRmsEligibilityKey()")
    assert 'b.operation === "rms"' in body
    assert "Nominal frequency must be a positive number." in body


def test_eligibility_check_uses_stale_response_guard():
    # Section 62: the same generation-counter idiom used elsewhere in this
    # file (wwCursorValuesGeneration / wwPeakValuesGeneration) for
    # discarding a superseded async response.
    source = _source()
    body = _function_body(source, "async function wwCcCheckRmsEligibility()", "function wwCcRenderRmsEligibilityStatus()")
    assert "wwCcRmsEligibilityGeneration" in body
    assert "generation" in body
    assert "superseded while in flight" in body


def test_eligibility_check_is_debounced():
    source = _source()
    body = _function_body(source, "function wwCcScheduleRmsEligibilityCheck()", "async function wwCcCheckRmsEligibility()")
    assert "setTimeout(wwCcCheckRmsEligibility, 400)" in body
    assert "clearTimeout(" in body


def test_eligibility_status_never_shows_numeric_confidence():
    # Section 45: categorical copy only.
    source = _source()
    body = _function_body(source, "function wwCcRenderRmsEligibilityStatus()", "function wwCcRmsBlocksCreate()")
    assert "%" not in body
    assert "suitable for RMS" in body


def test_create_blocked_helper_enforces_override_policy():
    source = _source()
    body = _function_body(source, "function wwCcRmsBlocksCreate()", "// --")
    assert 'wwCcRmsEligibility.status === "suitable"' in body
    assert "wwCcBuilder.override" in body
    assert "wwCcRmsEligibility.loading" in body
    assert "checkedForKey" in body


def test_sync_create_button_state_consults_rms_guard():
    source = _source()
    body = _function_body(source, "function wwCcSyncCreateButtonState()", "function wwCcSelectOperation(operation)")
    assert "wwCcRmsBlocksCreate()" in body


def test_select_operation_resets_rms_fields():
    source = _source()
    body = _function_body(source, "function wwCcSelectOperation(operation)", "function wwCcAddInputByKey(key)")
    assert 'wwCcBuilder.nominalFrequency = "50";' in body
    assert "wwCcBuilder.override = false;" in body
    assert "wwCcResetRmsEligibility();" in body


def test_add_input_triggers_eligibility_check_for_rms():
    source = _source()
    body = _function_body(source, "function wwCcAddInputByKey(key)", "function wwCcRemoveInput(index)")
    assert 'wwCcBuilder.operation === "rms"' in body
    assert "wwCcScheduleRmsEligibilityCheck();" in body


def test_render_builder_fields_delegates_rms_parameters_to_dedicated_function():
    source = _source()
    body = _function_body(source, "function wwCcRenderBuilderFields()", "function wwCcRenderExpressionPreview()")
    assert "wwCcRenderRmsParameterFields()" in body


def test_create_channel_sends_override_flag_and_rms_parameters():
    # Section 43: the backend must receive an explicit override flag it
    # independently validates -- the frontend never omits it or trusts a
    # locally-computed eligibility result instead of sending one.
    source = _source()
    body = _function_body(source, "async function wwCcCreateChannel()", "async function wwCcDeleteChannel(calculatedChannelId)")
    assert 'nominal_frequency_hz: Number(wwCcBuilder.nominalFrequency)' in body
    assert "override: override" in body
    assert "wwCcRmsBlocksCreate()" in body


def test_create_channel_request_body_always_includes_override_key():
    # Regardless of operation, the POST body must always carry `override`
    # (defaulting false) -- never a conditionally-omitted field the
    # backend's Pydantic schema would otherwise default silently in a way
    # the frontend can't observe.
    source = _source()
    body = _function_body(source, "async function wwCcCreateChannel()", "async function wwCcDeleteChannel(calculatedChannelId)")
    assert "override: override" in body
    assert "const override = wwCcBuilder.operation === \"rms\" ? !!wwCcBuilder.override : false;" in body


# ----------------------------------------------------------------------
# Phase 5B UAT Enhancement (DEC-048 clarification): parameter-authority UI
# ----------------------------------------------------------------------


def test_source_inventory_caches_nominal_frequency_with_no_new_network_call():
    source = _source()
    body = _function_body(source, "ww.sourceChannelInventory.set(sourceId, {", "wwRememberSourceTimingFromChannelsData(data);")
    assert "nominalFrequency: data.source.nominal_frequency" in body


def test_nominal_frequency_authority_resolver_covers_source_and_calculated_inputs():
    source = _source()
    body = _function_body(
        source, "function wwCcResolveNominalFrequencyAuthority(inputCandidate)", "function wwInfoTipHtml(ariaLabel, text)"
    )
    assert 'inputCandidate.kind === "source"' in body
    assert "calc.reference_source_id" in body
    assert '"metadata"' in body
    assert '"user"' in body
    # Section 19: never inferred from engineering_type.
    assert "engineering_type" not in body


def test_builder_state_defaults_nominal_frequency_source_to_user():
    source = _source()
    body = _function_body(source, "const wwCcBuilder = {", "const wwCcListErrors")
    assert 'nominalFrequencySource: "user"' in body


def test_reset_and_select_operation_reset_nominal_frequency_source():
    source = _source()
    reset_body = _function_body(source, "function wwCcResetBuilder()", "function wwCcResolveNominalFrequencyAuthority")
    select_op_body = _function_body(source, "function wwCcSelectOperation(operation)", "function wwCcAddInputByKey(key)")
    assert 'wwCcBuilder.nominalFrequencySource = "user";' in reset_body
    assert 'wwCcBuilder.nominalFrequencySource = "user";' in select_op_body


def test_add_input_refreshes_nominal_frequency_authority():
    # Section 29: switching input must refresh authority, not just leave a
    # stale value/source tag from the previous input in place.
    source = _source()
    body = _function_body(source, "function wwCcAddInputByKey(key)", "function wwCcRemoveInput(index)")
    assert "wwCcResolveNominalFrequencyAuthority(candidate)" in body
    assert 'authority.source === "metadata"' in body
    assert 'wwCcBuilder.nominalFrequencySource = "metadata";' in body
    assert 'wwCcBuilder.nominalFrequencySource = "user";' in body


def test_info_tip_trigger_is_keyboard_and_screen_reader_accessible():
    source = _source()
    body = _function_body(source, "function wwInfoTipHtml(ariaLabel, text)", "function wwInfoTipShow(trigger)")
    assert "<button" in body  # a real, tabbable control -- not a bare <span> or <div>
    assert "aria-label=" in body
    assert 'aria-describedby="wwInfoTipPortal"' in body
    assert "data-tooltip-text=" in body


def test_info_tip_portal_markup_exists_at_body_level():
    # Phase 5B UAT Fix: the tooltip BODY is a single shared node placed
    # near the end of <body> (not nested inside any scrolling ancestor),
    # so it can never be clipped by a page-specific overflow container.
    source = _source()
    assert 'id="wwInfoTipPortal"' in source
    assert 'role="tooltip"' in source
    portal_markup = source[source.index('id="wwInfoTipPortal"') - 60 : source.index('id="wwInfoTipPortal"') + 60]
    assert "hidden" in portal_markup
    # Must not be nested inside the Calculated Channels page's own
    # scrolling container -- the exact root cause this fix addresses.
    assert source.index('id="wwInfoTipPortal"') > source.index('id="pageCalculatedChannels"')
    assert source.index('id="wwInfoTipPortal"') < source.index('vendor/plotly/plotly-cartesian.min.js')


def test_info_tip_portal_css_is_fixed_positioned_and_theme_token_based():
    source = _source()
    css = source[source.index(".ww-info-tip-portal {") : source.index(".ww-info-tip-portal[hidden]") + 60]
    assert "position: fixed" in css
    # Theme-token-based, not hardcoded colors -- correct in Light and Dark
    # automatically, same convention as every other themed surface here.
    assert "var(--panel)" in css
    assert "var(--text)" in css
    assert "var(--panel-border)" in css
    # A considered value on the app's own existing z-index scale (see the
    # code comment for why 50, not an arbitrary huge number).
    assert "z-index: 50" in css


def test_info_tip_no_longer_relies_on_inline_sibling_bubble():
    # Regression test for the actual root cause: an inline `position:
    # absolute` bubble next to each trigger was silently clipped by
    # #pageCalculatedChannels's own `overflow: auto` -- confirmed via
    # direct browser measurement, not assumed. The fix must not
    # reintroduce that structure.
    source = _source()
    assert ".ww-info-tip-bubble" not in source
    assert "ww-info-tip-trigger:hover +" not in source


def test_info_tip_show_hide_use_fixed_positioning_computed_from_trigger():
    source = _source()
    body = _function_body(source, "function wwInfoTipShow(trigger)", "function wwInfoTipHide()")
    assert "getBoundingClientRect()" in body
    assert "portal.style.top" in body
    assert "portal.style.left" in body
    assert "portal.hidden = false;" in body


def test_info_tip_events_are_delegated_on_document_for_dynamic_triggers():
    # RMS parameter fields are wholesale re-rendered on every input/
    # frequency change -- a per-element listener would silently break
    # the moment its own trigger button is replaced. Delegation on
    # `document` covers every current and future trigger.
    source = _source()
    body = _function_body(source, "document.addEventListener(\"mouseover\"", "function wwCcResetRmsEligibility()")
    assert 'document.addEventListener("mouseover"' in body
    assert 'document.addEventListener("mouseout"' in body
    assert 'document.addEventListener("focusin"' in body
    assert 'document.addEventListener("focusout"' in body
    assert "wwInfoTipShow(trigger)" in body
    assert "wwInfoTipHide()" in body


def test_rms_parameter_fields_distinguish_all_four_authority_categories():
    source = _source()
    body = _function_body(source, "function wwCcRenderRmsParameterFields()", "// ---")

    # Category A/B: Nominal Frequency is EITHER the constrained dropdown
    # (user-selectable, only 50/60 Hz, never free text) OR a readonly
    # metadata display -- never both rendered as identical text boxes.
    assert 'wwCcBuilder.nominalFrequencySource === "metadata"' in body
    assert "wwCcNominalFrequencySelect" in body
    assert '<option value="50"' in body
    assert '<option value="60"' in body
    assert "From recording metadata" in body
    assert "Select nominal system frequency" in body
    assert 'inputmode="decimal"' not in body  # no free-text numeric entry anywhere in this block

    # Category C: Window is always readonly and derived, never editable.
    assert "readonly tabindex=\"-1\" value=\"1 cycle (" in body

    # Category D: Method is fixed, readonly, never a dropdown -- exactly
    # one <select> in this whole block (Nominal Frequency's own, only
    # ever present in "user" mode), never a second one for Method.
    assert 'value="True RMS"' in body
    assert body.count("<select") == 1

    # All three (Nominal Frequency, Window, Method) get an info-tip.
    assert body.count("wwInfoTipHtml(") == 3


def test_window_tooltip_explains_automatic_derivation():
    source = _source()
    body = _function_body(source, "function wwCcRenderRmsParameterFields()", "// ---")
    assert "calculated automatically from the nominal frequency" in body


def test_method_tooltip_explains_true_rms_in_plain_language():
    source = _source()
    body = _function_body(source, "function wwCcRenderRmsParameterFields()", "// ---")
    assert "DC offset and harmonics are included" in body


def test_nominal_frequency_select_change_updates_window_via_full_rerender():
    source = _source()
    body = _function_body(source, "wwCcBuilderFields\").addEventListener(\"change\"", "wwCcBuilderFields\").addEventListener(\"input\"")
    assert 'event.target.id === "wwCcNominalFrequencySelect"' in body
    assert "wwCcBuilder.nominalFrequency = event.target.value;" in body
    assert "wwCcRenderBuilderFields();" in body
    assert "wwCcScheduleRmsEligibilityCheck();" in body
    # The old free-text input id must be fully retired from event wiring.
    assert "wwCcNominalFrequencyInput" not in body


def test_readonly_fields_get_distinct_visual_treatment_not_just_dimmer_text():
    # Section 15/16: an automatic field must look different BEFORE
    # interaction, not merely have a slightly dimmer font color.
    source = _source()
    rule = source[source.index('.ww-cc-field input[readonly] {') : source.index("}", source.index('.ww-cc-field input[readonly] {'))]
    assert "background" in rule


def test_guardrails_unchanged_eligibility_and_override_still_wired():
    # Section 28: this UI restructuring must not regress metadata-first
    # waveform_form eligibility, the detector fallback, RMS-of-RMS
    # protection, or the override checkbox.
    source = _source()
    eligibility_body = _function_body(source, "async function wwCcCheckRmsEligibility()", "function wwCcRenderRmsEligibilityStatus()")
    assert "rms-eligibility" in eligibility_body
    assert "wwCcRmsEligibilityGeneration" in eligibility_body
    blocks_body = _function_body(source, "function wwCcRmsBlocksCreate()", "function wwCcRenderRmsParameterFields()")
    assert 'wwCcRmsEligibility.status === "suitable"' in blocks_body
    assert "wwCcBuilder.override" in blocks_body
