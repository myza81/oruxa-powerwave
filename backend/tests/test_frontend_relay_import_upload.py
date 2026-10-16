"""Static structural checks for the Relay Import Slice 3 UI (frontend/index.html).

Same source-text assertion pattern as the other test_frontend_*.py files.
Real fetch/render/interaction behaviour is covered by
browser-tests/relay_import_upload.spec.js.
"""

from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _slice(source: str, start: str, end: str) -> str:
    i = source.index(start)
    return source[i : source.index(end, i)]


def _relay_import_js(source: str) -> str:
    return _slice(source, "const wwRelayImportState", "function wwDistanceSetInputSource")


def _distance_panel(source: str) -> str:
    return _slice(source, 'id="wwDistancePanel"', 'id="wwDistanceManualInputSection"')


class TestEntryPoint:
    def test_import_control_is_inside_the_distance_panel_and_named_correctly(self):
        panel = _distance_panel(_source())
        assert 'id="wwRelayImportBtn"' in panel
        assert ">Import Relay Settings<" in panel
        assert "Import PDF" not in _source()

    def test_manual_workflow_is_not_nested_in_or_gated_by_the_import_panel(self):
        panel = _distance_panel(_source())
        import_panel = _slice(panel, 'id="wwRelayImportPanel"', "</section>")
        assert "wwDistanceBody" not in import_panel
        assert 'id="wwDistanceBody"' in panel
        assert 'id="wwDistanceZone1ReachInput"' in panel
        assert 'id="wwDistanceInputSourceManualBtn"' in panel

    def test_privacy_wording_present_and_accurate(self):
        panel = _distance_panel(_source())
        assert "Files are processed temporarily and are not permanently stored." in panel
        assert "cleared when you refresh or close this tab" in panel

    def test_file_input_accepts_pdf_only_and_is_a_single_file(self):
        panel = _distance_panel(_source())
        tag = re.search(r'<input type="file" id="wwRelayImportFileInput"[^>]*>', panel).group(0)
        assert 'accept=".pdf,application/pdf"' in tag
        assert "multiple" not in tag

    def test_remove_control_and_status_regions_exist(self):
        panel = _distance_panel(_source())
        for element_id in ("wwRelayImportRemoveBtn", "wwRelayImportFilename", "wwRelayImportStatus", "wwRelayImportError"):
            assert f'id="{element_id}"' in panel
        assert 'role="alert"' in _slice(panel, 'id="wwRelayImportError"', ">")


class TestPanelPolish:
    def test_import_control_is_a_standard_button_not_a_segmented_toggle(self):
        panel = _distance_panel(_source())
        tag = re.search(r'<button[^>]*id="wwRelayImportBtn"[^>]*>', panel).group(0)
        assert 'type="button"' in tag
        assert "ww-oc-axis-toggle-btn" not in tag  # default (primary) app button

    def test_remove_uses_the_secondary_button_style(self):
        panel = _distance_panel(_source())
        tag = re.search(r'<button[^>]*id="wwRelayImportRemoveBtn"[^>]*>', panel).group(0)
        assert 'class="secondary"' in tag

    def test_heading_hint_and_privacy_are_separate_elements(self):
        panel = _slice(_distance_panel(_source()), 'id="wwRelayImportPanel"', "</section>")
        assert ">Relay Settings</h3>" in panel
        assert "PDF supported for now. Manual entry remains available below." in panel
        assert 'class="ww-relay-import-privacy"' in panel
        assert panel.index("wwRelayImportFile\"") < panel.index("wwRelayImportPrivacy")

    def test_file_card_groups_type_name_status_and_remove(self):
        card = _slice(_distance_panel(_source()), 'id="wwRelayImportFile"', 'id="wwRelayImportError"')
        for element_id in ("wwRelayImportType", "wwRelayImportFilename", "wwRelayImportStatus", "wwRelayImportDetail", "wwRelayImportRemoveBtn"):
            assert f'id="{element_id}"' in card

    def test_filename_truncates_safely_and_exposes_full_name(self):
        source = _source()
        css = _slice(source, ".ww-relay-import-filename {", "}")
        assert "text-overflow: ellipsis" in css and "overflow: hidden" in css and "white-space: nowrap" in css
        assert "min-width: 0" in _slice(source, ".ww-relay-import-info {", "}")
        assert "nameEl.title = " in _relay_import_js(source)

    def test_accepted_state_reports_extraction_not_interpretation_and_import_disables_while_processing(self):
        js = _relay_import_js(_source())
        assert "Text extracted. Relay settings have not been interpreted yet." in js
        assert "PDF accepted, but no extractable text was found. OCR is not supported yet." in js
        assert "PDF is encrypted and cannot be read." in js
        assert "raw entr" in js and '" pages"' in js
        assert "importBtn.disabled = state.phase === \"uploading\"" in js

    def test_button_states_defined(self):
        source = _source()
        assert "#wwRelayImportBtn:hover" in source
        assert "#wwRelayImportBtn:focus-visible" in source


class TestIdentificationDisplay:
    """Slice 5: identity is named; nothing is interpreted or auto-filled."""

    def test_identity_line_sits_between_filename_and_status(self):
        card = _slice(_distance_panel(_source()), 'id="wwRelayImportFile"', 'id="wwRelayImportError"')
        assert card.index("wwRelayImportFilename") < card.index("wwRelayImportIdentity") < card.index("wwRelayImportStatus")
        assert ".ww-relay-import-identity:empty { display: none; }" in _source()

    def test_messages_for_each_outcome(self):
        js = _relay_import_js(_source())
        assert "Relay identified. Settings have not been interpreted yet." in js
        assert "Relay identification needs confirmation." in js
        assert "Relay model not recognised. You can continue with manual entry." in js
        assert 'filter(Boolean).join(" \u00b7 ")' in js  # "Siemens · 7SA613"

    def test_unidentified_fallback_keeps_the_extraction_message(self):
        assert "Text extracted. Relay settings have not been interpreted yet." in _relay_import_js(_source())

    def test_only_the_verdict_fields_are_read_from_the_response(self):
        js = _relay_import_js(_source())
        for field in ("identification_status", "manufacturer", "model"):
            assert f"body.{field}" in js
        for forbidden in ("body.evidence", "body.candidates", "body.profile_id", "Validated", "validated"):
            assert forbidden not in js

    def test_identification_state_is_cleared_with_the_rest(self):
        js = _relay_import_js(_source())
        reset = js[js.index("function wwRelayImportReset"): js.index("function wwRelayImportRender")]
        for field in ("identificationStatus", "manufacturer", "model"):
            assert f"wwRelayImportState.{field} =" in reset

    def test_identification_never_touches_the_distance_form(self):
        js = _relay_import_js(_source())
        for forbidden in ("wwDistanceZone", "wwDistanceState", "Input.value"):
            assert forbidden not in js


class TestInterpretationDisplay:
    """Slice 6: an interpretation SUMMARY is shown; nothing is applied."""

    def test_summary_line_sits_after_the_detail_line(self):
        card = _slice(_distance_panel(_source()), 'id="wwRelayImportFile"', 'id="wwRelayImportError"')
        assert card.index("wwRelayImportDetail") < card.index("wwRelayImportSummary") < card.index("wwRelayImportRemoveBtn")
        assert '.ww-relay-import-detail:empty { display: none; }' in _source()

    def test_messages_make_clear_it_was_interpreted_but_not_applied(self):
        js = _relay_import_js(_source())
        assert (
            "Relay identified and settings interpreted. Review is required before applying. "
            "Nothing has been applied to the form."
        ) in js
        assert "Relay identified, but no distance zones could be interpreted." in js
        assert "Relay identified, but its settings could not be interpreted." in js
        # Identification-only relays keep their Slice 5 wording.
        assert "Relay identified. Settings have not been interpreted yet." in js

    def test_summary_text_is_zones_mapped_and_the_uncertainty_categories(self):
        js = _relay_import_js(_source())
        for needle in (
            '"zone found"', '"zones found"', '"setting mapped"', '"settings mapped"', '"assumption"', '"assumptions"',
            '" missing"', '"conflict"', '"conflicts"', '" not yet supported"', '" unreadable"', '" unresolved"',
            '" documented relay behaviour"', '" approximate"', '"not a relay setting"', '"not relay settings"',
        ):
            assert needle in js, needle
        # the old catch-all wording is gone from the visible summary
        assert '" to confirm"' not in js

    def test_only_summary_counts_are_read_from_the_response(self):
        js = _relay_import_js(_source())
        for field in ("interpretation_status", "zone_count", "mapped_setting_count", "inferred_setting_count", "unresolved_setting_count"):
            assert f"body.{field}" in js
        for forbidden in ("interpretation_warnings", "body.profile_version", "Validated", "validated"):
            assert forbidden not in js

    def test_interpretation_state_is_cleared_with_the_rest(self):
        js = _relay_import_js(_source())
        clear = _slice(js, "function wwRelayImportClearInterpretation", "function wwRelayImportSummaryText")
        for needle in ('interpretationStatus = ""', "zoneCount = 0", "mappedCount = 0", "inferredCount = 0", "unresolvedCount = 0"):
            assert needle in clear
        reset = _slice(js, "function wwRelayImportReset", "function wwRelayImportRender")
        assert "wwRelayImportClearInterpretation(wwRelayImportState)" in reset
        handle = js[js.index("async function wwRelayImportHandleFile"):]
        assert "wwRelayImportClearInterpretation(state)" in handle

    def test_summary_is_rendered_as_text(self):
        js = _relay_import_js(_source())
        assert 'getElementById("wwRelayImportSummary").textContent = ' in js
        assert "innerHTML" not in js


class TestEphemeralState:
    def test_state_is_a_plain_in_memory_object_starting_idle(self):
        js = _relay_import_js(_source())
        assert 'phase: "idle"' in js

    def test_no_browser_storage_in_relay_import_code(self):
        js = _relay_import_js(_source())
        for forbidden in ("localStorage", "sessionStorage", "indexedDB", "caches.", "document.cookie"):
            assert forbidden not in js

    def test_reset_clears_every_field_and_the_file_input(self):
        js = _slice(_relay_import_js(_source()), "function wwRelayImportReset", "function wwRelayImportRender")
        for needle in ('phase = "idle"', 'filename = ""', 'sourceFormat = ""', "sizeBytes = 0", 'error = ""', "controller = null", 'input.value = ""'):
            assert needle in js
        assert "abort()" in js

    def test_relay_import_code_never_touches_distance_settings_state(self):
        js = _relay_import_js(_source())
        assert "wwDistanceState" not in js
        assert "wwDistanceZone" not in js

    def test_upload_posts_to_the_versioned_endpoint_with_a_single_file_field(self):
        js = _relay_import_js(_source())
        assert 'apiBaseUrl() + "/api/v1/relay-import/upload"' in js
        assert 'form.append("file"' in js

    def test_filename_is_rendered_as_text_not_html(self):
        js = _relay_import_js(_source())
        assert "nameEl.textContent = " in js
        assert 'getElementById("wwRelayImportFilename")' in js
        assert "innerHTML" not in js

    def test_event_wiring_present(self):
        source = _source()
        assert 'getElementById("wwRelayImportBtn").addEventListener("click"' in source
        assert 'getElementById("wwRelayImportFileInput").addEventListener("change"' in source
        assert 'getElementById("wwRelayImportRemoveBtn").addEventListener("click", wwRelayImportReset)' in source


class TestExtractionSummary:
    def test_summary_fields_are_taken_from_the_response_only(self):
        js = _relay_import_js(_source())
        for field in ("body.extraction_status", "body.page_count", "body.raw_entry_count"):
            assert field in js

    def test_reset_clears_extraction_state(self):
        js = _slice(_relay_import_js(_source()), "function wwRelayImportReset", "function wwRelayImportRender")
        for needle in ('extractionStatus = ""', "pageCount = 0", "rawEntryCount = 0"):
            assert needle in js

    def test_card_font_sizes(self):
        source = _source()
        assert "font-size: 0.7rem" in _slice(source, ".ww-relay-import-filename {", "}")
        assert "font-size: 0.7rem" in _slice(source, ".ww-relay-import-meta {", "}")
        assert "font-size: 0.6rem" in _slice(source, ".ww-relay-import-privacy {", "}")


def _review_js(source: str) -> str:
    return _slice(source, "const WW_RR_CATEGORY_LABELS", "function wwRelayImportReset")


class TestExtractionReview:
    """Slice 7: read-only Extraction Review. Behaviour is covered in
    browser-tests/relay_import_upload.spec.js; these guard the structure."""

    def test_review_entry_is_hidden_until_the_relay_is_interpreted(self):
        panel = _distance_panel(_source())
        assert re.search(r'<button type="button" id="wwRelayReviewBtn"[^>]*\bhidden\b[^>]*>Review Extracted Settings</button>', panel)
        js = _review_js(_source())
        assert 'state.interpretationStatus === "interpreted"' in js and "!!state.review" in js

    def test_review_panel_is_inside_the_import_panel_and_starts_hidden(self):
        panel = _slice(_distance_panel(_source()), 'id="wwRelayImportPanel"', 'id="wwDistanceBody"')
        assert re.search(r'id="wwRelayReviewPanel"[^>]*\bhidden\b', panel)
        assert 'id="wwRelayReviewCloseBtn"' in panel and 'id="wwRelayReviewBody"' in panel

    def test_there_is_no_apply_accept_or_populate_control_or_handler(self):
        source = _source()
        panel = _slice(_distance_panel(source), 'id="wwRelayImportPanel"', 'id="wwDistanceBody"')
        labels = re.findall(r"<button[^>]*>([^<]*)</button>", panel)
        assert labels, "the import panel has buttons"
        for label in labels:
            assert not re.search(r"apply|accept|populate|generate|auto-?fill", label, re.I), label
        js = _review_js(source)
        # Slice 9: the review reaches the manual form through ONE entry point (it validates the
        # backend payload and writes the same state manual entry uses); nothing else.
        assert js.count("wwDistanceApplyImportedSettings") == 1
        assert "wwDistance" not in js.replace("wwDistanceApplyImportedSettings", "")
        for forbidden in ("wwDistanceState", "wwDistanceZone", "wwDistanceHandleZoneSettingChanged", "wwDistanceRenderPlot"):
            assert forbidden not in js, forbidden

    def test_review_is_rendered_as_text_never_as_html(self):
        js = _review_js(_source())
        for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
            assert forbidden not in js

    def test_review_payload_is_held_in_tab_memory_and_cleared_with_everything_else(self):
        source = _source()
        assert "review: null" in _slice(source, "const wwRelayImportState", "function wwRelayImportClearInterpretation")
        clear = _slice(source, "function wwRelayImportClearInterpretation", "// \"5 zones found")
        assert "state.review = null" in clear and "state.reviewOpen = false" in clear
        assert "state.review = body.review || null" in source

    def test_status_labels_match_the_interpretation_vocabulary(self):
        js = _review_js(_source())
        # DEC-198 non-expert vocabulary: the internal category names never reach the normal UI
        assert 'mapped: "Mapped", documented: "Documented relay behaviour", approximate: "Approximate plot"' in js
        assert 'assumption: "Assumption", missing: "Source value missing", conflict: "Conflict"' in js
        assert 'unsupported: "Not yet supported", unverified: "Not yet supported", not_exposed: "Not a relay setting"' in js
        assert 'unreadable: "Unreadable"' in js
        assert 'confirmed: "Confirmed", resolved_manually: "Resolved manually"' in js
        assert "To confirm" not in js

    def test_ready_approximate_is_labelled_and_offers_apply(self):
        """DEC-198: the new readiness reads "Ready -- approximate plot" and, like Ready, shows Apply Settings."""
        js = _review_js(_source())
        assert 'ready_approximate: "Ready — approximate plot"' in js
        assert 'const WW_RR_APPLICABLE_READINESS = ["ready", "ready_approximate"];' in js
        assert "if (WW_RR_APPLICABLE_READINESS.includes(r.status)) {" in js
        # a reference and an approximation are explained in the Source disclosure
        assert 'labelled("Reference", ' in js and 'labelled("Relay settings", "unchanged")' in js

    def test_provenance_toggle_is_an_accessible_disclosure(self):
        js = _review_js(_source())
        for needle in ('setAttribute("aria-expanded"', 'setAttribute("aria-controls"', "prov.hidden = true"):
            assert needle in js

    def test_review_css_uses_shared_theme_tokens_only(self):
        source = _source()
        css = _slice(source, ":is(.ww-rr-panel) {", ".ww-oc-input-source-hint {")
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css)
        assert "animation" not in css and "transition" not in css
        assert "@media (max-width: 640px)" in css


class TestReviewConfirmation:
    """Slice 8: confirmation / manual resolution. Behaviour is covered in
    browser-tests/relay_import_review.spec.js; these guard the structure."""

    def test_decisions_are_tab_memory_only_and_cleared_with_everything_else(self):
        source = _source()
        state = _slice(source, "const wwRelayImportState", "function wwRelayImportClearInterpretation")
        assert "decisions:" in state and "reviewLive: null" in state
        clear = _slice(source, "function wwRelayImportClearInterpretation", "// \"5 zones found")
        for needle in ("state.decisions =", "state.reviewLive = null", "state.reviewController.abort()", "state.reviewBuilt = false"):
            assert needle in clear, needle
        js = _review_js(source)
        for forbidden in ("localStorage", "sessionStorage", "indexedDB", "document.cookie"):
            assert forbidden not in js, forbidden

    def test_validation_is_asked_of_the_backend_with_the_signed_token(self):
        js = _review_js(_source())
        assert '"/api/v1/relay-import/review/validate"' in js
        # DEC-198 Amendment 5: the opaque token and import id are returned unchanged; no interpretation JSON
        assert "validation_context" not in js
        for needle in ("validation_token: state.review.validation_token", "import_id: state.review.import_id",
                       "confirmed:", "manual:", "left_unresolved:"):
            assert needle in js, needle
        # the page never computes readiness or counts itself
        assert not re.search(r"readiness\.status\s*=[^=]", js)
        assert not re.search(r"(blocking|confirmed|to_confirm|unresolved)_count\s*=[^=]", js)

    def test_a_refused_decision_is_rolled_back(self):
        js = _review_js(_source())
        assert "state.decisions = wwRrCloneDecisions(state.reviewGood)" in js

    def test_a_stale_answer_is_discarded_by_version(self):
        js = _review_js(_source())
        assert "state.reviewVersion !== version" in js and "const version = ++state.reviewVersion" in js
        assert "state.reviewController.abort()" in js

    def test_readiness_is_never_read_through_a_possibly_missing_object(self):
        js = _review_js(_source())
        assert "live.readiness.status" not in js
        for needle in ("Re-evaluating…", "Not evaluated", "wwRrUsableState"):
            assert needle in js, needle

    def test_only_assumptions_and_resolvable_items_get_decision_controls(self):
        js = _review_js(_source())
        # Confirm needs the Assumption category, not merely an unconfirmed interpretation
        assert 'view.review_status === "to_confirm" && view.category === "assumption"' in js
        assert "if (wwRrConfirmable(view))" in js and "item.resolution" in js
        assert "Confirm all assumptions (" in js and "Confirm all inferred" not in js
        assert "const decidable = !!item.item_id && item.primary" in js

    def test_a_blank_entry_is_not_a_value(self):
        js = _review_js(_source())
        assert 'if (text === "")' in js and "Number(text)" in js

    def test_the_panel_is_refreshed_in_place(self):
        js = _review_js(_source())
        assert "state.reviewBuilt" in js and "wwRrRefreshAll" in js

    def test_there_is_still_no_apply_anywhere_in_the_import_panel(self):
        source = _source()
        js = _review_js(source)
        # the visible button vocabulary: no apply / populate / generate controls
        for label in re.findall(r'wwRrAction\("([^"]+)"', js) + re.findall(r'wwRrEl\("button", "ww-rr-btn", "([^"]+)"', js):
            assert not re.search(r"apply|populate|generate|plot|auto-?fill", label, re.I), label
