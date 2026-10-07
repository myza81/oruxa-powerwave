"""Static structural checks for the Oscillation Analysis navigation/page
shell (frontend/index.html). The shell is deliberately empty -- no signal
processing -- so these also guard against processing scope creeping in
before owner UAT. Interaction is covered by
browser-tests/phasor_analysis.spec.js ("analyzer menu ...")."""

from __future__ import annotations

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


def test_panel_is_an_empty_shell():
    panel = _between('id="wwOscillationPanel"', "</p>")
    assert "Oscillation Analysis" in panel
    for forbidden in ("<select", "<input", "<button", "plotly", "<canvas", "<svg"):
        assert forbidden not in panel.lower()
