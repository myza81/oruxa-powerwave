"""Static regression checks for the calculated-channel Null Handling UI
(DEC-084 Calc Slice 3). Same source-text substring-assertion pattern as
test_frontend_rms_calculated_channel.py -- this repo has no browser/DOM
test runner for the single-file frontend (see browser-tests/
calculated-channel-null-handling.spec.js for the real-browser
counterpart, which exercises the actual live validation/create/manager-
display behavior end to end).
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


def test_null_policy_config_matches_backend_wire_values():
    # Section 1: object keys are the wire values sent to the backend --
    # must match app.domain.calculated_channel.ALL_NULL_POLICIES exactly.
    source = _source()
    body = _function_body(source, "const WW_CC_NULL_POLICIES = {", "const WW_CC_ESTIMATION_METHODS = {")
    for policy in ("propagate_null", "treat_null_as_zero", "estimate_missing_data", "require_manual_value"):
        assert policy + ":" in body


def test_estimation_methods_config_excludes_pchip():
    # Section 2/22: only the four implemented methods are ever offered.
    source = _source()
    body = _function_body(source, "const WW_CC_ESTIMATION_METHODS = {", "const WW_CC_ESTIMATION_METHOD_ORDER")
    for method in ("hold_last", "nearest", "linear", "local_mean"):
        assert method + ":" in body
    assert "pchip" not in body

    order_line = source[source.index("const WW_CC_ESTIMATION_METHOD_ORDER"):source.index("\n", source.index("const WW_CC_ESTIMATION_METHOD_ORDER"))]
    assert "pchip" not in order_line
    assert '"hold_last", "nearest", "linear", "local_mean"' in order_line


def test_null_handling_select_exists_with_four_options_no_pchip():
    # Section 5: the <select> itself, hardcoded options -- a fixed,
    # backend-defined closed set.
    source = _source()
    start = source.index('id="wwCcNullPolicySelect"')
    end = source.index("</select>", start)
    block = source[start:end]
    assert 'value="propagate_null"' in block and "Propagate Null" in block
    assert 'value="treat_null_as_zero"' in block and "Treat Null as Zero" in block
    assert 'value="estimate_missing_data"' in block and "Estimate Missing Data" in block
    assert 'value="require_manual_value"' in block and "Require Manual Value" in block
    assert "pchip" not in block


def test_builder_state_has_null_handling_fields_with_propagate_default():
    # Section 4: backward-compatible Propagate Null default.
    source = _source()
    body = _function_body(source, "const wwCcBuilder = {", "const wwCcListErrors")
    assert 'nullPolicy: "propagate_null"' in body
    assert 'estimationMethod: ""' in body
    assert 'maxGapValue: ""' in body
    assert 'maxGapUnit: "samples"' in body
    assert 'localMeanRadius: ""' in body


def test_reset_builder_resets_null_handling_fields_to_propagate_default():
    source = _source()
    body = _function_body(source, "function wwCcResetBuilder()", "function wwCcResolveNominalFrequencyAuthority(inputCandidate)")
    assert 'wwCcBuilder.nullPolicy = "propagate_null";' in body
    assert 'wwCcBuilder.estimationMethod = "";' in body
    assert 'wwCcBuilder.maxGapValue = "";' in body
    assert 'wwCcBuilder.maxGapUnit = "samples";' in body
    assert 'wwCcBuilder.localMeanRadius = "";' in body


def test_estimation_fields_are_conditional_on_estimate_policy():
    # Section 7: only rendered when Estimate Missing Data is selected.
    source = _source()
    body = _function_body(source, "function wwCcRenderEstimationFields()", "function wwCcRenderOperationCards()")
    assert 'wwCcBuilder.nullPolicy !== "estimate_missing_data"' in body
    assert 'container.innerHTML = "";' in body
    assert "wwCcMaxGapValueInput" in body
    assert "wwCcEstimationMethodSelect" in body


def test_local_mean_radius_is_conditional_on_local_mean_method():
    # Section 10: only rendered for Local Mean, never Hold Last/Nearest/Linear.
    source = _source()
    body = _function_body(source, "function wwCcRenderEstimationFields()", "function wwCcRenderOperationCards()")
    assert 'wwCcBuilder.estimationMethod === "local_mean"' in body
    assert "wwCcLocalMeanRadiusInput" in body


def test_max_gap_uses_samples_only_no_ms_sec_dropdown():
    # Section 9: a fixed "samples" suffix, never a unit dropdown.
    source = _source()
    body = _function_body(source, "function wwCcRenderEstimationFields()", "function wwCcRenderOperationCards()")
    assert '<span class="ww-pu-suffix">samples</span>' in body
    assert "milliseconds" not in body
    assert "<select" not in body.split("Maximum Gap")[1].split("</label>")[0]


def test_null_policy_select_switch_clears_estimation_fields():
    # Section 11: switching away from Estimate must clear (not merely
    # hide) the stale estimation fields.
    source = _source()
    body = _function_body(
        source,
        'document.getElementById("wwCcNullPolicySelect").addEventListener("change"',
        'document.getElementById("wwCcEstimationFields").addEventListener("change"',
    )
    assert 'wwCcBuilder.nullPolicy !== "estimate_missing_data"' in body
    assert 'wwCcBuilder.estimationMethod = "";' in body
    assert 'wwCcBuilder.maxGapValue = "";' in body
    assert 'wwCcBuilder.localMeanRadius = "";' in body


def test_estimation_method_switch_away_from_local_mean_clears_radius():
    # Section 11: Local Mean -> Linear must ensure local_mean_radius is
    # never sent.
    source = _source()
    body = _function_body(
        source,
        'document.getElementById("wwCcEstimationFields").addEventListener("change"',
        'document.getElementById("wwCcEstimationFields").addEventListener("input"',
    )
    assert 'wwCcBuilder.estimationMethod !== "local_mean"' in body
    assert 'wwCcBuilder.localMeanRadius = "";' in body


def test_validate_builder_requires_null_policy_and_estimation_fields():
    # Section 12.
    source = _source()
    body = _function_body(source, "function wwCcValidateBuilder()", "function wwCcRmsEligibilityKey()")
    assert "Choose a null-handling policy." in body
    assert 'b.nullPolicy === "estimate_missing_data"' in body
    assert "Choose an estimation method." in body
    assert "Maximum Gap must be a positive whole number of samples." in body
    assert '!Number.isInteger(maxGap)' in body
    assert 'b.estimationMethod === "local_mean"' in body
    assert "Local Mean Radius must be a positive whole number of samples." in body
    assert '!Number.isInteger(radius)' in body


def test_create_channel_sends_null_policy_and_omits_estimation_fields_otherwise():
    # Section 13/23: null_policy always sent; estimation fields OMITTED
    # (never sent as null) for every other policy, matching this same
    # function's own existing `parameters = {}` omission convention.
    source = _source()
    body = _function_body(source, "async function wwCcCreateChannel()", "async function wwCcDeleteChannel(calculatedChannelId)")
    assert "null_policy: wwCcBuilder.nullPolicy," in body
    assert 'wwCcBuilder.nullPolicy === "estimate_missing_data"' in body
    assert "requestBody.estimation_method = wwCcBuilder.estimationMethod;" in body
    assert "requestBody.max_gap_value = Number(wwCcBuilder.maxGapValue);" in body
    assert "requestBody.max_gap_unit = wwCcBuilder.maxGapUnit;" in body


def test_create_channel_sends_local_mean_radius_only_for_local_mean():
    # Section 13: Local Mean sends radius; every other method (including
    # Linear) never does.
    source = _source()
    body = _function_body(source, "async function wwCcCreateChannel()", "async function wwCcDeleteChannel(calculatedChannelId)")
    assert 'wwCcBuilder.estimationMethod === "local_mean"' in body
    assert "requestBody.local_mean_radius = Number(wwCcBuilder.localMeanRadius);" in body
    # The radius line must be nested inside the local_mean-only branch,
    # not the outer estimate_missing_data branch alone.
    local_mean_idx = body.index('wwCcBuilder.estimationMethod === "local_mean"')
    radius_idx = body.index("requestBody.local_mean_radius")
    assert local_mean_idx < radius_idx


def test_create_channel_reuses_structured_error_display():
    # Section 14/15: no new error-formatting layer -- the existing
    # #wwCcError structured area already shows the backend's own message
    # verbatim for every new error code (require_manual_value_null,
    # invalid_null_policy, invalid_estimation_method,
    # estimation_method_not_implemented, invalid_max_gap_value,
    # invalid_max_gap_unit, invalid_local_mean_radius all reach it
    # identically via body.detail.message).
    source = _source()
    body = _function_body(source, "async function wwCcCreateChannel()", "async function wwCcDeleteChannel(calculatedChannelId)")
    assert "body.detail.message" in body
    assert 'errorEl.textContent = message; errorEl.hidden = false;' in body


def test_manager_list_shows_compact_null_policy_summary():
    # Section 18.
    source = _source()
    body = _function_body(source, "function wwCcNullPolicySummaryText(calc)", "function wwCcEnsureSelection()")
    assert '"Null: Propagate"' in body
    assert '"Null: Treat as Zero"' in body
    assert '"Null: Require Manual"' in body
    assert '"Missing data: "' in body
    assert '", radius "' in body


def test_manager_row_rendering_includes_null_policy_summary():
    source = _source()
    body = _function_body(source, "function wwRenderCalculatedChannelManagerList()", "function wwRenderCalculatedChannelsPage()")
    assert "wwCcNullPolicySummaryText(calc)" in body


def test_expression_text_for_is_not_altered_by_null_policy():
    # Section 20: null policy is calculation configuration, never part
    # of the formula text itself. Bounded to the function's own closing
    # brace (not the next signature) so the FOLLOWING function's own
    # comment block -- which legitimately explains why it is separate
    # from this one -- is never accidentally included in the check.
    source = _source()
    start = source.index("function wwCcExpressionTextFor(calc)")
    end = source.index("\n        }", start) + len("\n        }")
    body = source[start:end]
    assert "null_policy" not in body
    assert "estimation_method" not in body


def test_select_operation_does_not_reset_null_policy():
    # Null handling is operation-independent -- switching which
    # operation card is selected must not discard an already-configured
    # policy (unlike constant/nominalFrequency/override, which ARE
    # operation-specific and are reset here).
    source = _source()
    body = _function_body(source, "function wwCcSelectOperation(operation)", "function wwCcAddInputByKey(key)")
    assert "wwCcBuilder.nullPolicy" not in body
    assert "wwCcRenderNullPolicyField();" in body


def test_render_null_policy_field_syncs_select_and_hint():
    source = _source()
    body = _function_body(source, "function wwCcRenderNullPolicyField()", "function wwCcRenderEstimationFields()")
    assert 'getElementById("wwCcNullPolicySelect")' in body
    assert 'getElementById("wwCcNullPolicyHint")' in body
    assert "wwCcRenderEstimationFields();" in body
