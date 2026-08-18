"""Tests for app.domain.digital_classification.classify_digital_channel.

Covers the owner's exact classification precedence (Phase 4A task spec
sections 56-57): Spare (name-based, takes precedence) -> Triggered
(any non-zero sample anywhere in the full record) -> Never Triggered.
"""

from __future__ import annotations

import pytest

from app.domain.digital_classification import (
    KNOWN_GROUPS,
    NEVER_TRIGGERED,
    SPARE,
    TRIGGERED,
    classify_digital_channel,
)


class TestTriggeredClassification:
    def test_single_high_sample_is_triggered(self):
        # Section 56.A: name = "CB TRIP", values = [0,0,1,0]
        assert classify_digital_channel(name="CB TRIP", values=[0, 0, 1, 0]) == TRIGGERED

    def test_always_high_is_triggered_not_only_transitions(self):
        # Section 56.B / 41: a channel that never transitions but is high
        # for the entire record is STILL Triggered -- "has been high at
        # least once," not "contains a 0->1 transition."
        assert classify_digital_channel(name="52A CLOSED", values=[1, 1, 1, 1]) == TRIGGERED

    def test_high_at_first_sample_only(self):
        assert classify_digital_channel(name="X", values=[1, 0, 0, 0]) == TRIGGERED

    def test_high_at_last_sample_only(self):
        assert classify_digital_channel(name="X", values=[0, 0, 0, 1]) == TRIGGERED

    def test_non_binary_positive_value_counts_as_high(self):
        # Preserve truthful state interpretation for unexpected values --
        # any non-zero value counts as high, never silently ignored.
        assert classify_digital_channel(name="X", values=[0, 2, 0]) == TRIGGERED


class TestNeverTriggeredClassification:
    def test_all_zero_is_never_triggered(self):
        # Section 56.C: name = "BLOCKING", values = [0,0,0,0]
        assert classify_digital_channel(name="BLOCKING", values=[0, 0, 0, 0]) == NEVER_TRIGGERED

    def test_empty_values_is_never_triggered(self):
        assert classify_digital_channel(name="EMPTY", values=[]) == NEVER_TRIGGERED


class TestSpareClassification:
    def test_spare_all_zero(self):
        # Section 56.D: name = "SPARE 01", values = [0,0,0]
        assert classify_digital_channel(name="SPARE 01", values=[0, 0, 0]) == SPARE

    def test_spare_with_high_state_still_spare(self):
        # Section 56.E / 42: name-based Spare takes precedence over a
        # high/triggered state -- "Spare Trip" with values including 1 is
        # STILL Spare, never Triggered.
        assert classify_digital_channel(name="Spare Trip", values=[0, 1, 0]) == SPARE

    def test_spare_precedence_edge_case_spare_trip_high(self):
        # Section 42, explicit duplicate of the owner's own edge case:
        # name = "SPARE TRIP", values include 1 -> still Spare.
        assert classify_digital_channel(name="SPARE TRIP", values=[1, 1, 1]) == SPARE

    @pytest.mark.parametrize(
        "name", ["SPARE", "Spare 01", "spare_trip", "CB Spare Input", "spAre input"]
    )
    def test_case_insensitive_and_substring_spare_names(self, name):
        # Section 56.F / owner examples: case-insensitive, substring match.
        assert classify_digital_channel(name=name, values=[0, 0]) == SPARE

    def test_spare_substring_anywhere_in_name(self):
        assert classify_digital_channel(name="TRIP_SPARE_INPUT_02", values=[1]) == SPARE


class TestKnownGroupsOrder:
    def test_known_groups_are_triggered_never_triggered_spare_in_order(self):
        assert KNOWN_GROUPS == (TRIGGERED, NEVER_TRIGGERED, SPARE)
