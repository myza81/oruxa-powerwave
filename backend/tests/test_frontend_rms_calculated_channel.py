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


def test_render_builder_fields_renders_rms_controls():
    source = _source()
    body = _function_body(source, "function wwCcRenderBuilderFields()", "function wwCcRenderExpressionPreview()")
    assert "wwCcNominalFrequencyInput" in body
    assert "wwCcRmsEligibilityStatus" in body
    assert "wwCcRmsOverrideCheckbox" in body
    assert "wwCcRmsOverrideRow" in body


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
