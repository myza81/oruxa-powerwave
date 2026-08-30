"""Static regression checks for TG-H's per-Time-Group annotation
placement/anchoring/reprojection migration.

Governing principle under test throughout this file (the task's own
verbatim rule): "An annotation must always use the time transform and
plot geometry of the panel and Time Group it actually belongs to --
never the primary Time Group by default."

Root cause fixed this slice: `wwWireAnalogPanelClick()`'s Callout branch,
`wwCreatePeakFromClick()`'s own search-range, `wwAnchoredAnnotationPagePosition()`'s
own X projection, `wwRecalculateAllPeakAnnotations()`'s own recalculation
sweep, `wwAnnotationMetaLine()`/`wwPeakLabelLines()`'s own Absolute-time
text, and `wwWireCalloutAnchorDrag()`'s own drag-to-reposition all either
used `wwPrimaryTimeGroupId()`/the single global `ww.viewport` directly,
or (the drag case) called `wwCursorPlotMetrics()`/`wwCursorPixelXToTime()`
with NO groupId argument at all (a complete no-op bug, not merely
primary-scoped). Annotation ownership is derived FRESH every call from
the annotation's own stable `data.sourceId` (via
`wwTimeGroupIdForDisplaySourceId()`) -- never a stored/stale groupId,
since Time Group ids are themselves derived and can change after a
merge/split.

Mirrors this suite's own established pure string/index-based approach
(test_frontend_time_group_t0.py, test_frontend_time_group_layout.py) --
no jsdom execution. Real multi-group visual/interaction behavior is
proven live via Playwright against a running backend -- see this task's
own live-UAT report for the full record.

Case-letter references (A-O) below refer to TG-H's own section 24
required-test list.
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


# ==============================================================================
# Cases A/B: Callout placement resolves the CLICKED panel's own Time
# Group, never wwPrimaryTimeGroupId().
# ==============================================================================


class TestCalloutPlacementUsesTheClickedPanelsOwnGroup:
    def test_callout_branch_derives_groupid_from_the_clicked_panel(self):
        source = _source()
        fn_idx = source.index("function wwWireAnalogPanelClick(panel)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'if (type === "callout") {' in fn_body
        assert "const clickGroupId = wwPanelTimeGroupId(panel);" in fn_body
        assert "wwPlotlyXToElapsed(clickGroupId, point.x)" in fn_body

    def test_callout_placement_no_longer_calls_wwprimarytimegroupid(self):
        source = _source()
        fn_idx = source.index("function wwWireAnalogPanelClick(panel)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwPrimaryTimeGroupId()" not in fn_body


# ==============================================================================
# Case D: t0 set/clear never mutates a stored anchor -- only its
# displayed pixel/text mapping changes.
# ==============================================================================


class TestT0ChangesNeverMutateStoredAnnotationAnchors:
    def test_set_t0_for_group_never_touches_ww_annotations(self):
        source = _source()
        fn_body = _function_body(
            source,
            "async function wwSetT0FromCursorAForGroup(groupId)",
            "async function wwClearT0ForGroup(groupId)",
        )
        assert "ww.annotations" not in fn_body
        assert "anchorElapsedSeconds" not in fn_body
        assert "peakElapsedSeconds" not in fn_body

    def test_clear_t0_for_group_never_touches_ww_annotations(self):
        source = _source()
        fn_body = _function_body(
            source,
            "async function wwClearT0ForGroup(groupId)",
            "function wwHandleSetOrClearT0ClickForGroup(groupId)",
        )
        assert "ww.annotations" not in fn_body
        assert "anchorElapsedSeconds" not in fn_body
        assert "peakElapsedSeconds" not in fn_body

    def test_anchored_annotation_time_reads_the_raw_stored_field_only(self):
        """wwAnchoredAnnotationTime() is the ONE place anchorElapsedSeconds/
        peakElapsedSeconds are read for projection -- confirms no t0 math
        (wwWorkspaceTimeToEventTime/wwEventTimeToWorkspaceTime) happens
        here; the physical anchor stays a plain workspace-time number,
        t0-invariant by construction."""
        source = _source()
        fn_idx = source.index("function wwAnchoredAnnotationTime(annotation)")
        fn_body = source[fn_idx : fn_idx + 300]
        assert "data.anchorElapsedSeconds" in fn_body
        assert "data.peakElapsedSeconds" in fn_body
        assert "wwWorkspaceTimeToEventTime" not in fn_body
        assert "wwEventTimeToWorkspaceTime" not in fn_body
        assert "wwT0ForGroup" not in fn_body


# ==============================================================================
# Case E: Absolute/Elapsed display-mode switch never re-anchors an
# annotation -- wwCursorTimeToPixelX()'s own fractional-position math
# (which wwAnchoredAnnotationPagePosition() reuses) never reads
# ww.timeMode at all.
# ==============================================================================


class TestDisplayModeSwitchNeverReanchorsAnnotations:
    def test_cursor_time_to_pixel_x_is_mode_agnostic(self):
        source = _source()
        fn_idx = source.index("function wwCursorTimeToPixelX(groupId, time)")
        fn_body = source[fn_idx : fn_idx + 500]
        assert "ww.timeMode" not in fn_body

    def test_set_time_mode_never_touches_ww_annotations(self):
        source = _source()
        fn_idx = source.index("function wwSetTimeMode(mode)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "ww.annotations" not in fn_body
        assert "wwCreateAnnotation" not in fn_body


# ==============================================================================
# Cases B/C/F/I: Peak annotation placement AND ongoing recalculation
# (zoom/pan/reset) use the clicked/owning panel's own Time Group range,
# never the single global ww.viewport.
# ==============================================================================


class TestPeakAnnotationsUseTheirOwnGroupsRange:
    def test_peak_placement_derives_range_from_the_clicked_panels_own_group(self):
        source = _source()
        fn_idx = source.index("async function wwCreatePeakFromClick(panel, channel, mode)")
        fn_body = source[fn_idx : fn_idx + 1200]
        assert "const clickGroupId = wwPanelTimeGroupId(panel);" in fn_body
        assert "const clickRange = wwTimeGroupVisibleRange(clickGroupId);" in fn_body
        assert "if (!clickRange) return;" in fn_body
        assert "const startTime = clickRange.start;" in fn_body
        assert "const endTime = clickRange.end;" in fn_body
        # The DEC-061-adjacent old expression must be gone.
        assert "if (!ww.viewport) return;" not in fn_body
        assert "const startTime = ww.viewport.start;" not in fn_body

    def test_recalculate_all_peak_annotations_requires_an_explicit_group_and_filters_by_it(self):
        source = _source()
        fn_idx = source.index("function wwRecalculateAllPeakAnnotations(groupId, startTime, endTime)")
        fn_body = source[fn_idx : fn_idx + 700]
        assert "wwTimeGroupIdForDisplaySourceId(data.sourceId) !== groupId" in fn_body

    def test_viewport_change_recalculates_peaks_unconditionally_per_group(self):
        """Case F: previously gated `if (isPrimary)`, now called
        unconditionally with THIS group's own just-applied range -- a
        non-primary group's own zoom/pan/reset now recalculates its OWN
        Peak annotations, and can never reach another group's."""
        source = _source()
        fn_idx = source.index("async function wwApplyAndFetchGroupViewport(groupId, startTime, endTime)")
        fn_body = source[fn_idx : source.index("async function wwApplyAndFetchViewport(startTime, endTime)", fn_idx)]
        primary_idx = fn_body.index("if (isPrimary) {")
        primary_end = fn_body.index("ww.viewport = { start: startTime, end: endTime };", primary_idx) + len(
            "ww.viewport = { start: startTime, end: endTime };"
        )
        primary_block = fn_body[primary_idx:primary_end]
        unconditional_tail = fn_body[primary_end:]
        assert "wwRecalculateAllPeakAnnotations" not in primary_block
        assert "wwRecalculateAllPeakAnnotations(groupId, startTime, endTime);" in unconditional_tail


# ==============================================================================
# Case J: reprojection resolves EACH annotation's own group independently
# (never a shared/cached groupId across annotations in one render pass).
# ==============================================================================


class TestReprojectionResolvesEachAnnotationsOwnGroupIndependently:
    def test_page_position_derives_groupid_fresh_from_this_annotations_own_source(self):
        source = _source()
        fn_idx = source.index("function wwAnchoredAnnotationPagePosition(annotation)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const groupId = wwTimeGroupIdForDisplaySourceId(data.sourceId);" in fn_body
        assert "const range = wwTimeGroupVisibleRange(groupId);" in fn_body
        assert "wwCursorTimeToPixelX(groupId, time)" in fn_body
        # The X geometry (groupId-derived) and Y geometry (entry.panel,
        # this annotation's own ACTUAL panel) now come from the SAME
        # resolved ownership -- the old cross-group X/Y mismatch is
        # structurally impossible.
        assert "wwAnchorValueToPixelY(entry.panel, value)" in fn_body
        assert "wwPrimaryTimeGroupId()" not in fn_body
        assert "ww.viewport" not in fn_body

    def test_render_annotations_is_a_flat_per_annotation_loop_no_group_filter_needed(self):
        """wwRenderAnnotations() itself never branches on Time Group --
        each annotation's own call to wwAnchoredAnnotationPagePosition()
        resolves independently, so two groups' own annotations render
        correctly side by side with zero cross-contamination risk."""
        source = _source()
        fn_idx = source.index("function wwRenderAnnotations()")
        fn_body = source[fn_idx : fn_idx + 900]
        assert "for (const annotation of ww.annotations.values())" in fn_body
        assert "wwPrimaryTimeGroupId" not in fn_body


# ==============================================================================
# Cases E (text)/L: Absolute-mode DISPLAY TEXT for a Callout/Peak also
# uses that annotation's own group's origin, not the workspace/
# first-displayed-channel default.
# ==============================================================================


class TestAnnotationDisplayTextUsesItsOwnGroupsOrigin:
    def test_meta_line_passes_groupid_to_absolute_formatting(self):
        source = _source()
        fn_idx = source.index("function wwAnnotationMetaLine(annotation)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const groupId = wwTimeGroupIdForDisplaySourceId(data.sourceId);" in fn_body
        assert "wwFormatAbsoluteElapsedTime(data.anchorElapsedSeconds, { groupId: groupId, spanSeconds: wwVisibleSpanSeconds(groupId) })" in fn_body
        assert "wwFormatAbsoluteElapsedTime(data.peakElapsedSeconds, { groupId: groupId, spanSeconds: wwVisibleSpanSeconds(groupId) })" in fn_body

    def test_peak_label_lines_passes_groupid_to_absolute_formatting(self):
        source = _source()
        fn_idx = source.index("function wwPeakLabelLines(annotation)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const groupId = wwTimeGroupIdForDisplaySourceId(data.sourceId);" in fn_body
        assert "wwFormatAbsoluteElapsedTime(data.peakElapsedSeconds, { groupId: groupId, spanSeconds: wwVisibleSpanSeconds(groupId) })" in fn_body


# ==============================================================================
# Callout anchor drag-to-reposition: fixed alongside the placement/
# reprojection bugs -- this call site passed wwCursorPlotMetrics()/
# wwCursorPixelXToTime() NO groupId argument at all (not merely
# primary-scoped -- a complete no-op, since no real group id could ever
# match `undefined`/a raw pixel number).
# ==============================================================================


class TestCalloutAnchorDragResolvesItsOwnAnnotationsGroup:
    def test_pointerdown_derives_and_stores_the_draggeded_annotations_own_group(self):
        source = _source()
        fn_idx = source.index("function wwWireCalloutAnchorDrag()")
        fn_body = source[fn_idx : fn_idx + 12000]
        assert "let dragGroupId = null;" in fn_body
        assert "dragGroupId = wwTimeGroupIdForDisplaySourceId(annotation.data.sourceId);" in fn_body
        assert "dragMetrics = wwCursorPlotMetrics(dragGroupId);" in fn_body
        # The old broken no-arg call must be gone.
        assert "wwCursorPlotMetrics();" not in fn_body

    def test_pointerup_resolves_time_using_the_stored_drag_group(self):
        source = _source()
        fn_idx = source.index("function wwWireCalloutAnchorDrag()")
        fn_body = source[fn_idx : fn_idx + 12000]
        assert "wwCursorPixelXToTime(dragGroupId, event.clientX, dragMetrics)" in fn_body
        # The old broken 2-arg call (groupId slot filled by a raw pixel
        # value) must be gone.
        assert "wwCursorPixelXToTime(event.clientX, dragMetrics)" not in fn_body


# ==============================================================================
# Case O: static "no primary fallback" sweep -- every per-annotation
# placement/anchoring/reprojection function touched this slice must
# never call wwPrimaryTimeGroupId().
# ==============================================================================


class TestNoPrimaryGroupFallbackInPerAnnotationCode:
    FUNCTIONS = [
        ("function wwWireAnalogPanelClick(panel)", "\n        }\n"),
        ("async function wwCreatePeakFromClick(panel, channel, mode)", "\n        }\n"),
        ("function wwAnchoredAnnotationPagePosition(annotation)", "\n        }\n"),
        ("function wwRecalculateAllPeakAnnotations(groupId, startTime, endTime)", "\n        }\n"),
        ("function wwAnnotationMetaLine(annotation)", "\n        }\n"),
        ("function wwPeakLabelLines(annotation)", "\n        }\n"),
    ]

    def test_no_per_annotation_function_calls_wwprimarytimegroupid(self):
        source = _source()
        for signature, terminator in self.FUNCTIONS:
            fn_idx = source.index(signature)
            fn_body = source[fn_idx : source.index(terminator, fn_idx)]
            assert "wwPrimaryTimeGroupId()" not in fn_body, (
                signature + " must never call wwPrimaryTimeGroupId()"
            )

    def test_callout_anchor_drag_wiring_calls_wwprimarytimegroupid_nowhere(self):
        source = _source()
        fn_idx = source.index("function wwWireCalloutAnchorDrag()")
        fn_body = source[fn_idx : fn_idx + 12000]
        assert "wwPrimaryTimeGroupId()" not in fn_body
