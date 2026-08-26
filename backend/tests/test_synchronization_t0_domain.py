"""Pure domain tests for the Slice 2 (explicit common event t=0) additions
to app.domain.synchronization: workspace_time_to_event_time()/
event_time_to_workspace_time(), and the full composed source<->event
mapping built from Slice 1's + Slice 2's own pure functions together.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.domain.synchronization import (
    event_time_to_workspace_time,
    source_time_to_workspace_time,
    workspace_time_to_event_time,
    workspace_time_to_source_time,
)


class TestWorkspaceEventConversion:
    def test_positive_t0(self):
        assert workspace_time_to_event_time(0.6, 0.5) == pytest.approx(0.1)
        assert event_time_to_workspace_time(0.1, 0.5) == pytest.approx(0.6)

    def test_zero_t0(self):
        assert workspace_time_to_event_time(0.6, 0.0) == pytest.approx(0.6)
        assert event_time_to_workspace_time(0.6, 0.0) == pytest.approx(0.6)

    def test_negative_event_position(self):
        """A workspace time BEFORE the event origin must yield a
        negative event time."""
        assert workspace_time_to_event_time(0.4, 0.5) == pytest.approx(-0.1)
        assert event_time_to_workspace_time(-0.1, 0.5) == pytest.approx(0.4)

    def test_negative_workspace_position(self):
        assert workspace_time_to_event_time(-0.2, 0.5) == pytest.approx(-0.7)
        assert event_time_to_workspace_time(-0.7, 0.5) == pytest.approx(-0.2)

    def test_round_trip_is_exact_for_any_t0(self):
        for workspace_time, t0 in [(0.0, 0.5123456), (10.0, -0.2), (-5.0, 1.5), (0.5, 0.5)]:
            event_time = workspace_time_to_event_time(workspace_time, t0)
            assert event_time_to_workspace_time(event_time, t0) == pytest.approx(workspace_time)

    def test_array_conversion(self):
        workspace = np.array([0.4, 0.5, 0.6])
        event = workspace_time_to_event_time(workspace, 0.5)
        np.testing.assert_allclose(event, np.array([-0.1, 0.0, 0.1]), atol=1e-12)
        back = event_time_to_workspace_time(event, 0.5)
        np.testing.assert_allclose(back, workspace)


class TestComposedSourceEventMapping:
    """event_time = source_time + alignment_offset_s - t0_workspace_time,
    composed from the two independent pure-function pairs (Slice 1's
    source<->workspace, Slice 2's workspace<->event) -- never a third,
    separately-coded formula. These tests exercise the composition the
    way every real caller (frontend wwSourceTimeToEventTime()/
    wwEventTimeToSourceTime()) is expected to build it."""

    def _source_to_event(self, source_time, alignment_offset_s, t0):
        workspace_time = source_time_to_workspace_time(source_time, alignment_offset_s)
        return workspace_time_to_event_time(workspace_time, t0)

    def _event_to_source(self, event_time, alignment_offset_s, t0):
        workspace_time = event_time_to_workspace_time(event_time, t0)
        return workspace_time_to_source_time(workspace_time, alignment_offset_s)

    def test_zero_source_offset(self):
        event_time = self._source_to_event(0.512345, 0.0, 0.5)
        assert event_time == pytest.approx(0.012345)
        assert self._event_to_source(event_time, 0.0, 0.5) == pytest.approx(0.512345)

    def test_positive_source_offset(self):
        # Source B, offset +0.401 s (the task's own worked example).
        source_time = 0.11134  # -> workspace_time 0.51234
        event_time = self._source_to_event(source_time, 0.401, 0.51234)
        assert event_time == pytest.approx(0.0, abs=1e-9)
        assert self._event_to_source(event_time, 0.401, 0.51234) == pytest.approx(source_time)

    def test_negative_source_offset(self):
        event_time = self._source_to_event(0.7, -0.2, 0.4)
        assert event_time == pytest.approx(0.1)
        assert self._event_to_source(event_time, -0.2, 0.4) == pytest.approx(0.7)

    def test_non_zero_t0_with_various_offsets(self):
        for source_time, offset, t0 in [(0.0, 0.0, 0.25), (1.0, 0.5, 0.25), (-1.0, -0.3, 0.25)]:
            event_time = self._source_to_event(source_time, offset, t0)
            recovered = self._event_to_source(event_time, offset, t0)
            assert recovered == pytest.approx(source_time)

    def test_full_formula_matches_direct_arithmetic(self):
        """Cross-checks the composed helpers against the task's own
        explicit flat formula: event_time = source_time + offset - t0."""
        source_time, offset, t0 = 0.837, 0.0185, 0.5123456
        expected = source_time + offset - t0
        assert self._source_to_event(source_time, offset, t0) == pytest.approx(expected)
