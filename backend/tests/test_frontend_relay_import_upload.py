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

    def test_accepted_state_says_settings_not_read_and_import_disables_while_processing(self):
        js = _relay_import_js(_source())
        assert "File accepted" in js
        assert "Settings have not been read yet." in js
        assert "importBtn.disabled = state.phase === \"uploading\"" in js

    def test_button_states_defined(self):
        source = _source()
        assert "#wwRelayImportBtn:hover" in source
        assert "#wwRelayImportBtn:focus-visible" in source


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
