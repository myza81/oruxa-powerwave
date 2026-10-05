"""Static regression checks for the removal of "Synchronize Sources"
from Waveform (owner ticket, Waveform toolbar refinement).

This file previously covered TG-F's per-Time-Group Synchronise Sources
migration (the modal, its per-canvas `.ww-tg-sync-btn` entry point, and
every function that only ever existed to drive it). That migration's
own subject was removed outright by a later owner ticket -- the modal
had exactly one caller (the button) and no other workflow reached any
of it, so once the button was removed the whole modal became genuinely
dead code, not merely superseded behaviour. Rather than keep ~25 tests
asserting things about functions that no longer exist, this file is
replaced with its removal's own confirmation coverage, mirroring the
"old global control removed" pattern this suite's own prior
TestOldGlobalControlRemoved class already established for an earlier
removal (the original workspace-wide #wwSyncBtn).

The underlying AUTOMATIC synchronization-state behaviour this modal
only ever let an engineer EDIT (alignment-offset fetch/apply at render
time, the sidebar's own per-source sync badge) is a separate mechanism
that was NOT touched -- see test_frontend_synchronization.py for its
own, still-full, regression coverage.
"""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


class TestSynchronizeSourcesRemoved:
    def test_no_markup_remains(self):
        """Markup-only check (ids/classes as they'd appear in an actual
        tag), not a blanket string ban -- several explanatory JS/HTML
        comments legitimately still name `.ww-tg-sync-btn`/#wwSyncOverlay
        historically (documenting what was removed and why), which is
        not itself live markup."""
        source = _source()
        for marker in (
            'id="wwSyncOverlay"',
            'id="wwSyncTitle"',
            'id="wwSyncGroupLabel"',
            'id="wwSyncError"',
            'id="wwSyncBody"',
            'id="wwSyncResetAllBtn"',
            'id="wwSyncCloseBtn"',
            'id="wwSyncCloseFooterBtn"',
            'class="ww-icon-btn ww-tg-sync-btn"',
        ):
            assert marker not in source, marker

    def test_no_dead_functions_remain(self):
        source = _source()
        for signature in (
            "function wwRenderSyncSourceRow(",
            "let wwSyncModalGroupId",
            "function wwSourcesForTimeGroup(",
            "function wwRenderSyncBody(",
            "async function wwSyncReloadAndRenderForGroup(",
            "async function wwOpenSyncModal(",
            "function wwCloseSyncModal(",
            "function wwSyncShowError(",
            "async function wwSyncApplyOffsetChangeSideEffectsForGroup(",
            "function wwRefreshSourceSyncBadges(",
            "async function wwSyncPutOffset(",
            "async function wwSyncSetOffsetMs(",
            "async function wwSyncStepOffset(",
            "async function wwSyncResetOffset(",
            "async function wwSyncResetAllForGroup(",
        ):
            assert signature not in source, signature

    def test_wire_time_group_toolbar_no_longer_opens_it(self):
        """The per-canvas wiring hook stays (kept for any future
        genuinely-local control), but no longer wires anything sync-
        related -- there is nothing local left to wire."""
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwOpenSyncModal" not in fn_body
        assert ".ww-tg-sync-btn" not in fn_body

    def test_start_new_workspace_no_longer_closes_the_modal(self):
        """wwClearWorkspace()'s own "Start New Workspace" branch used to
        defensively close the sync modal (in case it happened to be
        open) -- that call site is gone along with the modal itself, not
        left pointing at a now-nonexistent function."""
        source = _source()
        clear_idx = source.index("function wwClearWorkspace(options)")
        clear_body = source[clear_idx : source.index("// Phase 2C-C1", clear_idx)]
        assert "wwCloseSyncModal" not in clear_body
        # The state clears themselves are untouched -- see
        # test_frontend_synchronization.py's own coverage of this exact
        # block for the full assertion set.
        assert "ww.alignmentOffsets.clear()" in clear_body

    def test_ms_conversion_helpers_survive_for_event_reconstructions_own_unrelated_use(self):
        """wwSyncOffsetToMsDisplay()/wwSyncMsToOffsetSeconds() are the
        one exception to the removal: Event Reconstruction's own, wholly
        separate per-record manual correction feature
        (wwErFormatCorrection()/wwErSetCorrection()) reuses them
        directly, so they stay -- never modal-only despite the name."""
        source = _source()
        assert "function wwSyncOffsetToMsDisplay(offsetSeconds)" in source
        assert "function wwSyncMsToOffsetSeconds(ms)" in source
        assert "wwSyncOffsetToMsDisplay(correctionS)" in source
        assert "wwSyncMsToOffsetSeconds(ms)" in source
