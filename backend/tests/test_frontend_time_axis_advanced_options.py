"""Structural checks for the Advanced options follow-up to the Time Axis
Setup redesign: Reconstructed Time (`repeated_timestamp_precision_loss`)
and Manual Interpretation (`manual`) are removed from the normal "Time
format" dropdown's static option list and re-presented as two explained
cards under a collapsed "Advanced options" section, distinct from the
existing "Advanced details" (technical metadata) section.

Same static source-text convention every other test_frontend_*.py file
in this suite uses -- no JS execution engine is part of this repo's
test harness.
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


class TestNormalDropdownExcludesAdvancedInterpreters:
    def test_static_options_are_the_placeholder_plus_five_normal_formats(self):
        source = _source()
        body = _function_body(
            source, 'id="wwDataPrepTimeAxisInterpreterSelect">', "</select>",
        )
        # UAT fix: a neutral placeholder is the ONLY option with an
        # empty value -- never a real interpretation a fresh, never-
        # configured source could be mistaken for. Deliberately NOT
        # `disabled` -- a disabled <option> cannot actually be selected
        # by assigning `select.value = ""` in the browser (confirmed via
        # UAT), which would defeat restoring/displaying this state.
        assert '<option value="">' in body
        assert "<option value=\"\" disabled>" not in body
        assert 'value="absolute_datetime"' in body
        assert 'value="split_date_time"' in body
        assert 'value="time_of_day"' in body
        assert 'value="elapsed_numeric"' in body
        assert 'value="sample_index"' in body
        # The two moved-out interpreters must NOT be static options.
        assert 'value="manual"' not in body
        assert 'value="repeated_timestamp_precision_loss"' not in body
        assert body.count("<option") == 6

    def test_backend_interpreter_ids_are_unchanged(self):
        # This is a user-facing reorganization only -- the same five ids
        # (plus the two moved-out ones, injected dynamically elsewhere)
        # must still be exactly what WW_DATA_PREP_SAMPLE_INTERPRETERS and
        # WW_DATA_PREP_INTERPRETER_LABELS already declare.
        source = _source()
        assert '"absolute_datetime", "split_date_time", "time_of_day", "elapsed_numeric", "sample_index",' in source
        assert '"repeated_timestamp_precision_loss",' in source
        assert 'manual: "Manual Interpretation",' in source
        assert 'repeated_timestamp_precision_loss: "Reconstructed Time",' in source


class TestAdvancedOptionsSection:
    def test_advanced_options_is_distinct_from_time_details(self):
        # Row 7 redesign (2026-09-07): the separate "Advanced details"
        # accordion (#wwDataPrepTimeAxisAdvanced) is retired -- its
        # useful fields consolidated into the new, always-visible Time
        # Details column instead. Advanced Options (still a collapsed
        # <details>, moved into the panel's header-right actions) and
        # Time Details (read-only technical facts) must never be merged
        # into one concept.
        source = _source()
        assert 'id="wwDataPrepTimeAxisAdvancedOptions"' in source
        assert 'id="wwDataPrepTimeAxisAdvanced"' not in source
        assert "Advanced Options" in source
        assert 'id="wwDataPrepTimeAxisDetailsCol"' in source
        # Distinct CSS classes -- never merged into one concept.
        assert 'class="ww-data-prep-time-axis-advanced-options"' in source
        assert 'class="ww-data-prep-time-axis-advanced"' not in source

    def test_both_cards_have_title_description_example_and_action(self):
        source = _source()
        body = _function_body(
            source,
            'id="wwDataPrepTimeAxisAdvancedOptions"',
            "</details>",
        )
        assert "<h4>Reconstructed Time</h4>" in body
        assert "insufficient" in body
        assert "Example:" in body and "18:04:00" in body
        assert 'id="wwDataPrepTimeAxisUseReconstructedBtn"' in body
        assert "<h4>Manual Interpretation</h4>" in body
        assert "engineer-defined interpretation" in body
        assert "vendor exports a custom timestamp format" in body
        assert 'id="wwDataPrepTimeAxisUseManualBtn"' in body

    def test_advanced_options_collapsed_by_default(self):
        source = _source()
        body = _function_body(
            source, 'id="wwDataPrepTimeAxisAdvancedOptions"', ">",
        )
        assert "open" not in body


class TestAdvancedInterpreterOptionInjection:
    """Applied-state restoration guardrail: an advanced interpreter must
    still be a valid, selectable <option> the moment it is genuinely the
    current interpreter (restored from an applied config, suggested by
    DEC-082, or explicitly chosen via Advanced options), even though it
    is never a static dropdown entry."""

    def test_ensure_present_helper_injects_and_cleans_up(self):
        source = _source()
        assert "function wwDataPrepEnsureInterpreterOptionPresent(interpreterId)" in source
        body = _function_body(
            source,
            "function wwDataPrepEnsureInterpreterOptionPresent(interpreterId)",
            "function wwDataPrepSelectAdvancedInterpreter(interpreterId)",
        )
        assert "WW_DATA_PREP_ADVANCED_INTERPRETERS" in body
        assert "createElement(\"option\")" in body
        assert "stale.remove();" in body

    def test_form_render_calls_ensure_present_before_assigning_value(self):
        # Restoring an applied advanced config must call this BEFORE
        # `select.value = interpreterId` -- assigning a value with no
        # matching <option> silently fails to select anything.
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderTimeAxisForm()", "async function wwDataPrepFetchTimeAxis()",
        )
        assert "wwDataPrepEnsureInterpreterOptionPresent(interpreterId)" in body
        idx_ensure = body.index("wwDataPrepEnsureInterpreterOptionPresent(interpreterId)")
        idx_assign = body.index('.value = interpreterId;')
        assert idx_ensure < idx_assign

    def test_fresh_unconfigured_source_defaults_to_the_neutral_placeholder(self):
        # UAT finding: defaulting to a REAL interpretation (either the
        # original "manual" fallback, or this task's own earlier
        # "absolute_datetime" fix) is itself wrong -- "Date & Time" would
        # imply Powerwave had already established an absolute datetime
        # axis for a source with no Time Axis configuration at all yet.
        # A genuinely-applied `manual` config must still restore as
        # manual; only the "nothing saved yet" case uses the placeholder.
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderTimeAxisForm()", "async function wwDataPrepFetchTimeAxis()",
        )
        assert 'interpreterId = "";' in body
        assert 'interpreterId = "manual";' in body

    def test_dec082_suggestion_handler_ensures_option_present(self):
        # A DEC-082 suggestion CAN legitimately be
        # repeated_timestamp_precision_loss (its allowed_families is
        # non-empty) -- must also be injected before selection.
        source = _source()
        body = _function_body(
            source,
            'getElementById("wwDataPrepTimeAxisDiagnostics").addEventListener("click"',
            "});",
        )
        assert "wwDataPrepEnsureInterpreterOptionPresent(btn.dataset.interpreterId);" in body


class TestAdvancedOptionsForceOpen:
    def test_interpreter_fields_render_force_opens_for_advanced_interpreters(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepRenderTimeAxisInterpreterFields()",
            "function wwDataPrepTimeAxisIndexIntervalSecondsFromForm()",
        )
        assert "WW_DATA_PREP_ADVANCED_INTERPRETERS.includes(interpreterId)" in body
        assert 'getElementById("wwDataPrepTimeAxisAdvancedOptions").open = true;' in body


class TestAdvancedOptionsExplicitActions:
    def test_use_reconstructed_time_button_selects_and_detects(self):
        source = _source()
        body = _function_body(
            source,
            'getElementById("wwDataPrepTimeAxisUseReconstructedBtn").addEventListener',
            'getElementById("wwDataPrepTimeAxisUseManualBtn").addEventListener',
        )
        assert 'wwDataPrepSelectAdvancedInterpreter("repeated_timestamp_precision_loss");' in body
        assert "wwDataPrepDetectTimeAxis();" in body

    def test_use_manual_button_selects_without_detecting(self):
        # Manual has no detect() concept at all -- matches the plain
        # interpreter-dropdown "change" listener's own behavior for it.
        source = _source()
        body = _function_body(
            source,
            'getElementById("wwDataPrepTimeAxisUseManualBtn").addEventListener',
            "document.getElementById(\"wwDataPrepTimeAxisDetails\").addEventListener",
        )
        assert 'wwDataPrepSelectAdvancedInterpreter("manual");' in body
        assert "wwDataPrepDetectTimeAxis()" not in body

    def test_select_advanced_interpreter_reuses_the_shared_selection_path(self):
        # Never a second, divergent selection implementation -- the same
        # field-visibility/detect-reset/live-refresh calls the plain
        # dropdown "change" listener already uses.
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepSelectAdvancedInterpreter(interpreterId)",
            "function wwDataPrepTimeAxisEligibleColumns()",
        )
        assert "wwDataPrepEnsureInterpreterOptionPresent(interpreterId);" in body
        assert "wwDataPrepRenderTimeAxisInterpreterFields();" in body
        assert "wwDataPrepRenderTimeAxisDetectResult(null, null);" in body
        assert "wwDataPrepRefreshTimeAxisLiveState();" in body


class TestNeutralPlaceholderState:
    """UAT fix: a brand-new, never-configured source must not visually
    default to "Date & Time" (a real interpretation that could imply
    Powerwave already established an absolute datetime axis) -- a
    neutral "Select time format..." placeholder is used instead.
    Detection/recommendation stays entirely separate from selection
    (DEC-082's own "detected/recommended does not mean selected/applied"
    rule): the placeholder never auto-selects a detected/suggested
    interpreter, and clicking a "Use X" action is still the only thing
    that ever does."""

    def test_placeholder_hides_both_manual_and_detect_fields(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepRenderTimeAxisInterpreterFields()",
            "function wwDataPrepTimeAxisIndexIntervalSecondsFromForm()",
        )
        assert 'const isPlaceholder = interpreterId === "";' in body
        assert '"wwDataPrepTimeAxisNoFormatHint").hidden = !isPlaceholder;' in body
        assert '"wwDataPrepTimeAxisManualFields").hidden = isPlaceholder || isSample;' in body
        assert '"wwDataPrepTimeAxisDetectFields").hidden = isPlaceholder || !isSample;' in body

    def test_placeholder_hides_the_column_field_and_split_columns(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepRenderTimeAxisEligibleColumns()",
            "function wwDataPrepRenderTimeAxisManualColumnChecks(",
        )
        assert 'if (interpreterId === "") {' in body

    def test_column_indices_for_submit_returns_empty_for_placeholder(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepTimeAxisColumnIndicesForSubmit()",
            "function wwDataPrepRenderTimeAxisSummary()",
        )
        assert 'if (interpreterId === "") return [];' in body

    def test_save_guards_against_the_placeholder(self):
        source = _source()
        body = _function_body(
            source,
            "async function wwDataPrepSetTimeAxis()",
            "async function wwDataPrepClearTimeAxis()",
        )
        assert "if (!interpreterId) {" in body
        assert "Select a time format first." in body

    def test_placeholder_option_is_the_only_empty_value(self):
        source = _source()
        body = _function_body(
            source, 'id="wwDataPrepTimeAxisInterpreterSelect">', "</select>",
        )
        assert '<option value="">Select time format' in body

    def test_use_x_actions_remain_the_only_explicit_selection_path(self):
        # DEC-082: "Detected/recommended does not mean selected/applied."
        # Neither Advanced-options button nor the mismatch-suggestion
        # button ever fires on its own -- both are real user click
        # handlers, never invoked from a detect-result render.
        source = _source()
        detect_result_body = _function_body(
            source,
            "function wwDataPrepRenderTimeAxisDetectResult(detection, previewRows)",
            "function wwDataPrepRenderTimeAxisElapsedAndIndexFields(summary)",
        )
        assert "wwDataPrepSelectAdvancedInterpreter(" not in detect_result_body
        # Reading the current interpreter (a plain equality check, e.g.
        # deciding Manual's own confirmation wording) is fine; ASSIGNING
        # it from within a detect-result render is not -- that would be
        # exactly the silent-switch DEC-082 forbids.
        assert '.value = "' not in detect_result_body
