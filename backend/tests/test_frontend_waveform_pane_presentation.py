"""WUI-003 boundaries: pane/legend presentation cannot become engineering authority."""
from pathlib import Path
import re
import pytest

SOURCE = Path(__file__).resolve().parents[2] / 'frontend' / 'index.html'

def body(name):
    source = SOURCE.read_text(encoding='utf-8')
    return re.search(r'^        function ' + name + r'\b[^\n]*\{.*?^        }\n', source, re.M | re.S)[0]

@pytest.mark.parametrize('name', ['wwPaneLegendRecords', 'wwFitPaneLegend', 'wwOpenPaneLegendPopover', 'wwSyncWaveformPaneHeader'])
def test_presentation_never_fetches_or_recreates_the_waveform(name):
    code = body(name)
    for forbidden in ('fetch(', 'apiRequest(', 'Plotly.', 'wwRebuildLayout(', 'wwLoadChannelRange(', 'wwApplyUnitMode('):
        assert forbidden not in code

@pytest.mark.parametrize('name', ['wwRemovePanelDom', 'wwRebuildLayout', 'wwClearWorkspace'])
def test_every_pane_disposal_disconnects_presentation_resources(name):
    assert 'wwDisposePanePresentation(panel);' in body(name)

def test_observer_and_pending_frame_are_disposed_together():
    code = body('wwDisposePanePresentation')
    assert '.disconnect()' in code and 'cancelAnimationFrame(' in code
    assert 'wwHidePaneLegendTip(panel)' in code and 'wwClosePaneLegendPopover(panel)' in code

def test_floating_channel_list_exposes_only_canonical_visibility_not_configuration():
    code = body('wwOpenPaneLegendPopover')
    for forbidden in ('wwRemoveChannel', 'wwSetChannel', 'wwApplyUnitMode', 'ww-legend-remove', '<input', '<select'):
        assert forbidden not in code
    assert 'wwWireLegendToggle(panel, row)' in code

def test_record_labels_use_existing_rich_names_and_authoritative_recording_context():
    code = body('wwPaneLegendRecords')
    for helper in ('wwChannelDisplayNameHtml(', 'wwCalculatedChannelDisplayText(', 'recordingDisplayName(', 'wwRichLabelHtml(', 'wwDisplayedReference(', 'wwSourceCalibrationBadgeHtml('):
        assert helper in code
    assert '.channelName =' not in code and '.sourceId =' not in code

def test_legend_click_is_excluded_from_capture_before_annotation_creation():
    code = body('wwAnnotationPlacementClickHandler')
    assert code.index('.ww-pane-legend-popover') < code.index('wwCreateAnnotation(')

def test_separate_removal_stays_in_collapsed_legend_not_in_the_informational_popover():
    assert 'ww-legend-remove' in body('wwRenderLegend')
    assert 'wwRemoveChannelByKey(' in body('wwRenderLegend')


def test_legend_toggle_reuses_canonical_sidebar_handlers():
    code = body('wwToggleLegendChannel')
    assert 'wwToggleAnalogChannelDisplay(' in code
    assert 'wwToggleCalculatedChannelDisplay(' in code
    for forbidden in ('Plotly.', 'ww.displayed.set', 'ww.displayed.delete', 'panel.channels.push', 'fetch('):
        assert forbidden not in code


def test_native_controls_have_no_second_keyboard_activation_path():
    code = body('wwWireLegendToggle')
    assert "addEventListener('click'" in code
    assert 'event.repeat' in code
    assert code.count('wwToggleLegendChannel(') == 1


def test_last_channel_removal_remains_canonical_and_has_no_placeholder_pane():
    code = body('wwRemoveChannel')
    assert 'panel.channels.length === 0' in code
    assert 'wwRemovePanelDom(panel);' in code
    assert 'ww.displayed.delete(' in code


def test_owner_font_sizes_are_scoped_to_legend_controls():
    source = SOURCE.read_text(encoding='utf-8')
    start = source.index('/* WUI-003: presentation')
    end = source.index('.ww-panel--active', start)
    css = source[start:end]
    assert css.count('font-size: 0.65rem') >= 2
    assert 'font-size: 0.7rem' in css
    assert 'min-height: 24px' in css
