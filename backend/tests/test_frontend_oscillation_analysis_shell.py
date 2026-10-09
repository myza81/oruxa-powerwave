"""Static structural checks for the Oscillation Analysis navigation/page
page (frontend/index.html). The page is the SETUP/input workflow only -- no
signal processing -- so these also guard against processing scope creeping
in before owner UAT. Interaction is covered by
browser-tests/phasor_analysis.spec.js ("analyzer menu ...") and
browser-tests/oscillation_setup.spec.js."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
MANIFEST = (ROOT / "frontend" / "assets" / "icons" / "manifest.json").read_text(encoding="utf-8")


def _between(start: str, end: str) -> str:
    i = SOURCE.index(start)
    return SOURCE[i : SOURCE.index(end, i)]


def test_nav_button_is_last_analyzer_with_icon_and_label():
    nav = _between('class="ww-analysis-type-nav"', "</nav>")
    assert nav.index("Sequence Components") < nav.index("Oscillation Analysis")
    button = _between('id="wwAnalysisTypeOscillationBtn"', "</button>")
    assert 'data-analysis-type="oscillation"' in button
    assert 'data-ww-icon="ANALYSIS_OSCILLATION"' in button
    assert "<svg" not in button


def test_routed_through_shared_switcher():
    table = _between("const wwAnalysisPanelsByType", "function wwSetActiveAnalysisType")
    assert 'oscillation: "wwOscillationPanel"' in table
    assert 'getElementById("wwAnalysisTypeOscillationBtn")' in SOURCE


def test_icon_reuses_existing_owner_asset_and_is_in_manifest():
    assert 'ANALYSIS_OSCILLATION: "assets/icons/navigation/waveform_page.svg"' in SOURCE
    assert '"ANALYSIS_OSCILLATION"' in MANIFEST
    assert (ROOT / "frontend" / "assets" / "icons" / "navigation" / "waveform_page.svg").is_file()


def test_panel_has_setup_and_a_spectrum_card_but_no_interpretation_surface():
    panel = _between('id="wwOscillationPanel"', "<!-- Compliance & Capability, Slice 1")
    assert "Oscillation Analysis" in panel
    for heading in ("Analysis Setup", "Analysis Window", "Frequency Range", "Frequency Spectrum (Welch PSD)", "Display",
                    "Time-Frequency Spectrogram (STFT)", "Analysis Information", "Data Adequacy"):
        assert heading in panel
    # The result cards are hidden until Analyze; no static chart surface and no interpretation.
    assert 'id="wwOscSpectrumCard" hidden' in panel
    assert 'id="wwOscSpectrogramCard" hidden' in panel
    for forbidden in ("<canvas", "<svg", "dominant", "peak", "ringdown", "persistent"):
        assert forbidden not in panel.lower()


def _osc_script() -> str:
    return _between("// Oscillation Analysis -- SETUP / INPUT workflow", "wwOscInit();")


def test_signals_come_only_from_the_shared_live_catalogue():
    script = _osc_script()
    assert "wwSignalCatalogueList(" in script
    assert "wwSignalCatalogueSubscribe(" in script
    assert "wwSignalCatalogueIsCurrent(" in script
    # No private inventory and no hand-merge of the two authorities.
    for forbidden in ("sourceChannelInventory", "ww.calculatedChannels", "setInterval", "setTimeout"):
        assert forbidden not in script


def test_selection_stores_stable_key_and_revisions():
    script = _osc_script()
    for field in ("signalKey", "signalRevision", "catalogueRevision"):
        assert field in script


def test_adequacy_rule_constants_are_centralized():
    script = _osc_script()
    assert "const WW_OSC_ADEQUACY_RULES" in script
    assert "recommendedMinObservedCycles" in script
    assert "not a standard" in script


def test_no_processing_algorithm_is_present_in_the_browser():
    # Comments may name what is deliberately absent; only code is checked. The Welch PSD is
    # computed by the backend (DEC-174): the page only requests it and draws the returned arrays.
    script = "\n".join(
        line for line in _osc_script().lower().splitlines() if not line.strip().startswith("//")
    )
    # Candidate detection (DEC-175 [PROPOSAL]) is the backend's deterministic result: the page only draws the
    # returned evidence, so no peak-finding / prominence / spectral-estimation code may exist in it.
    for forbidden in ("fft", "prony", "damping", "float64array", "findpeaks", "find_peaks",
                      "argmax", "prominence(", "math.log(", "sinc", "ringdown"):
        assert forbidden not in script
    # The STFT (DEC-176 [PROPOSAL]) is the backend's too: no transform, window or slicing code in the page.
    for pattern in (r"(?<![a-z])stft\(", r"(?<![a-z])spectrogram\(", r"sliding", r"rfft"):
        assert not re.search(pattern, script), pattern
    assert "/oscillation-analysis/spectrum" in script
    # The candidate markers/list come only from the response's `detection` block.
    assert "result.detection" in script and "det.candidates" in script


def test_the_only_browser_maths_on_the_spectrogram_is_the_display_db_conversion():
    """DEC-176 [PROPOSAL]: the backend returns LINEAR PSD; the page converts to dB for display only, inside one
    function, with one global range (never per time slice) and nothing else."""
    script = chr(10).join(line for line in _osc_script().splitlines() if not line.strip().startswith("//"))
    assert script.count("Math.log10") == 2
    db = _between("function wwOscSpectrogramDb", "function wwOscSpectrogramDetailRows")
    assert db.count("Math.log10") == 2
    assert "/oscillation-analysis/spectrogram" in script and script.count("/oscillation-analysis/spectrogram") == 1
    # tied to the signal revision / setup exactly like the spectrum; candidates come from the spectrum result only
    for needle in ("wwOscRequestMatchesSetup(sg.request)", "wwSignalCatalogueIsCurrent(sg.request.signalKey, sg.request.signalRevision)",
                   "sp.request !== sg.request", "sp.result.detection.candidates"):
        assert needle in script, needle


def test_raw_vi_math_lives_in_the_backend_not_the_browser():
    """DEC-173: the RMS magnitude is derived by the existing backend RMS
    engine on demand. The page only requests its metadata and must not
    reimplement RMS/envelope mathematics or create a calculated channel."""
    script = chr(10).join(line for line in _osc_script().splitlines() if not line.strip().startswith("//"))
    assert "/oscillation-analysis/representation" in script
    for forbidden in ("Math.sqrt", "Math.sin", "Math.cos", "Math.PI", "sinc", "wwCalculatedChannelsUpsert",
                      "/calculated-channels", "wwFetchCalculatedChannels"):
        assert forbidden not in script, forbidden


def test_only_implemented_representations_are_declared():
    script = _osc_script()
    block = script[script.index("const WW_OSC_REPRESENTATIONS"): script.index("});", script.index("const WW_OSC_REPRESENTATIONS"))]
    assert "native" in block and "rms_magnitude" in block
    for not_implemented in ("positive_sequence", "phasor", "envelope", "derived_frequency", "power"):
        assert not_implemented not in block


def test_raw_vi_is_no_longer_reported_as_requiring_preprocessing():
    script = _osc_script()
    assert "Requires RMS/magnitude preprocessing" not in script
    assert "requires preprocessing" not in script.lower()
    assert 'reason: "form"' not in script


def test_spectrum_results_are_tied_to_the_signal_revision_and_setup():
    script = _osc_script()
    # Stale handling: key + revision via the shared catalogue, and the exact setup the result was computed for.
    for needle in ("wwOscSpectrumGuard", "wwSignalCatalogueIsCurrent(sp.request.signalKey, sp.request.signalRevision)",
                   "wwOscSpectrumSettingsMatch", "Analysis settings changed — run Analyze again", "sp.seq"):
        assert needle in script, needle


def test_spectrum_is_computed_only_on_analyze():
    script = _osc_script()
    assert script.count("/oscillation-analysis/spectrum") == 1
    run = _between("async function wwOscRunSpectrum", "function wwOscAnalyze()")
    assert "/oscillation-analysis/spectrum" in run
    # Only the Analyze click path starts a run.
    assert script.count("wwOscRunSpectrum(") == 2  # definition + the single call from wwOscAnalyze
