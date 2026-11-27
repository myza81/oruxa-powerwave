"""NF-3E static regression checks for the frontend: the single in-page notification after a nominal-frequency change, the metadata-only refresh,
the stale marker and one advisory (backend-derived, never computed in the page), the O-8 builder preselection and the declared basis.

Same source-text assertion pattern as test_frontend_rms_calculated_channel.py. The rendered behaviour is covered by
`browser-tests/nf3e-calculated-channel-staleness.spec.js`.
"""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _body(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    return source[start:source.index(next_signature, start)]


def test_a_successful_manual_or_auto_change_emits_one_notification_with_the_new_state():
    body = _body(_source(), "function wwRdNfEnqueue(bodyObject, done)", "function wwRdNfEffectiveMode()")
    assert body.count('new CustomEvent("nominal-frequency-changed"') == 1
    emit = body[body.index('new CustomEvent("nominal-frequency-changed"'):]
    for field in ("workspaceId", "sourceId", "revision", "effectiveHz", "origin"):
        assert field in emit[:400], field
    # emitted only on success (after `response.ok`), never for a refused change
    assert body.index("if (response.ok)") < body.index('new CustomEvent("nominal-frequency-changed"') < body.index("} else {")


def test_the_notification_refreshes_metadata_only_and_never_recomputes_or_refetches_waveforms():
    source = _source()
    start = source.index('document.addEventListener("nominal-frequency-changed"')
    handler = source[start:source.index("});", start)]
    assert "wwFetchCalculatedChannels()" in handler
    assert "wwCcLoadEffectiveFrequency(" in handler and "wwCcEffectiveFrequency.delete(" in handler
    for forbidden in ("/waveform", "method: \"POST\"", "wwCcCreateChannel", "calculated-channels/"):
        assert forbidden not in handler, forbidden


def test_the_stale_state_is_read_from_the_backend_never_derived_in_the_page():
    source = _source()
    helpers = _body(source, "function wwCcIsFrequencyStale(calc)", "function wwCalcChannelProvenanceBadgeHtml(calc)")
    assert "calc.frequency_staleness" in helpers and 'state === "stale"' in helpers
    assert "nominal_frequency_hz" not in helpers.split("function wwCcFrequencyAdvisoryText")[0]       # no comparison of stored vs effective
    assert "parameters" not in helpers                                                              # the page never looks at the stored parameters here


def test_the_list_row_shows_one_marker_and_one_advisory_only_for_a_stale_channel():
    body = _body(_source(), "function wwRenderCalculatedChannelManagerList()", "function wwRenderCalculatedChannelsPage()")
    assert body.count("wwCalcChannelFrequencyStaleBadgeHtml(calc)") == 1
    assert body.count('data-ww-freq-advisory="true"') == 1
    assert "wwCcIsFrequencyStale(calc) ?" in body


def test_the_marker_and_advisory_use_the_existing_warning_token_and_no_new_dialog_or_panel():
    source = _source()
    assert ".ww-calc-freq-stale-badge { font-size: 0.75em; margin-left: 0.3em; white-space: nowrap; color: var(--warn); }" in source
    assert ".ww-cc-list-row-advisory { grid-column: 1 / -1; color: var(--warn); font-size: 0.7rem; margin-top: 4px; }" in source
    assert "wwCcFrequencyAdvisoryText(" in source and "role=\"dialog\" id=\"wwCcFrequency" not in source


def test_the_advisory_names_the_reason_and_says_values_are_unchanged():
    body = _body(_source(), "function wwCcFrequencyAdvisoryText(calc)", "function wwCalcChannelFrequencyStaleBadgeHtml(calc)")
    assert "recording_frequency_unusable" in body and "no longer has a usable nominal frequency" in body
    assert "the recording's nominal frequency is now" in body and "Values are unchanged" in body
    assert "cause.own" in body and "Depends on" in body                                              # inherited staleness names its root cause


def test_a_create_request_declares_the_calculation_intent_from_the_builders_frequency_authority():
    source = _source()
    start = source.index('else if (wwCcBuilder.operation === "rms") {')
    payload = source[start:source.index('else if (wwCcBuilder.operation === "rocof")', start)]
    assert 'nominal_frequency_basis: wwCcBuilder.nominalFrequencySource === "metadata" ? "recording" : "explicit"' in payload


def test_an_explicit_selection_is_remembered_and_preserved_when_the_recordings_frequency_loads_later():
    source = _source()
    select = _body(source, 'event.target.id === "wwCcNominalFrequencySelect"', "wwCcResetRmsEligibility();")
    assert "wwCcBuilder.nominalFrequencyChosen = true;" in select
    reapply = _body(source, "function wwCcReapplyFrequencyAuthority(sourceId)", "function wwCcResolveNominalFrequencyAuthority(inputCandidate)")
    assert "b.nominalFrequencyChosen" in reapply.split("return")[0] + "return"


def test_the_builder_preselects_the_applicable_frequency_and_requires_an_explicit_choice_when_none_is_usable():
    source = _source()
    resolver = _body(source, "function wwCcResolveNominalFrequencyAuthority(inputCandidate)", "function wwInfoTipHtml(ariaLabel, text)")
    assert "effective.usable" in resolver and "unusable: true" in resolver
    apply_body = _body(source, "function wwCcApplyRmsFrequencyAuthority(candidate)", "function wwCcReapplyFrequencyAuthority(sourceId)")
    assert 'authority.unusable ? "" : "50"' in apply_body
    fields = _body(source, "function wwCcRenderRmsParameterFields()", "// Category C (automatically calculated)")
    assert 'value="" selected disabled>Select frequency</option>' in fields
    assert "Set in Recording Details" in fields and "Assumed (not declared by the recording)" in fields and "From recording metadata" in fields
