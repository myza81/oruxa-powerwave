"""PU-MIG S3 -- the pure lineage rule for the side of a calculated Voltage result (no registry, no API).

    every leaf strict-usable on ONE side  -> that side
    any leaf not strict-usable            -> not strict (historical Unverified, decision D-1 R+); the first problem in a fixed order
    strict leaves on DIFFERENT sides      -> refused `voltage_mixed_side`
    no leaves                             -> not strict (unresolved)
"""

from __future__ import annotations

import pytest

from app.domain.calculated_side_lineage import REASON_LEAF_SIDES_DIFFER, resolve_calculated_side
from app.domain.side_denominator import (
    PROBLEM_CALCULATED,
    PROBLEM_GROUP_CONFLICT,
    PROBLEM_INFERRED,
    PROBLEM_UNRESOLVED,
    SIDE_PRIMARY,
    SIDE_SECONDARY,
    SampleSide,
)


def strict(side, authority="recording_channel_declared"):
    return SampleSide(side=side, problem=None, authority=authority)


def problem(name):
    return SampleSide(side=None, problem=name, authority=None)


@pytest.mark.parametrize("side", [SIDE_PRIMARY, SIDE_SECONDARY])
@pytest.mark.parametrize("count", [1, 2, 3])
def test_all_leaves_strict_on_one_side_give_that_side(side, count):
    result = resolve_calculated_side([strict(side)] * count)
    assert result.refusal is None and (result.sample.side, result.sample.problem) == (side, None)


def test_strict_leaves_on_different_sides_are_refused_whatever_the_order():
    for leaves in ([strict(SIDE_PRIMARY), strict(SIDE_SECONDARY)], [strict(SIDE_SECONDARY), strict(SIDE_PRIMARY)],
                   [strict(SIDE_PRIMARY), strict(SIDE_PRIMARY), strict(SIDE_SECONDARY)]):
        result = resolve_calculated_side(leaves)
        assert result.sample is None and result.refusal == REASON_LEAF_SIDES_DIFFER == "voltage_mixed_side"


@pytest.mark.parametrize("bad", [PROBLEM_UNRESOLVED, PROBLEM_INFERRED, PROBLEM_GROUP_CONFLICT, PROBLEM_CALCULATED])
def test_one_non_strict_leaf_makes_the_whole_result_non_strict_even_beside_agreeing_strict_leaves(bad):
    for leaves in ([problem(bad), strict(SIDE_PRIMARY)], [strict(SIDE_PRIMARY), problem(bad), strict(SIDE_PRIMARY)]):
        result = resolve_calculated_side(leaves)
        assert result.refusal is None and result.sample.side is None and result.sample.problem == bad


def test_a_non_strict_leaf_wins_over_a_side_disagreement_so_nothing_is_refused_on_unverified_evidence():
    result = resolve_calculated_side([strict(SIDE_PRIMARY), strict(SIDE_SECONDARY), problem(PROBLEM_INFERRED)])
    assert result.refusal is None and result.sample.problem == PROBLEM_INFERRED


def test_the_reported_problem_is_deterministic_not_order_dependent():
    a = resolve_calculated_side([problem(PROBLEM_GROUP_CONFLICT), problem(PROBLEM_UNRESOLVED)])
    b = resolve_calculated_side([problem(PROBLEM_UNRESOLVED), problem(PROBLEM_GROUP_CONFLICT)])
    assert a.sample.problem == b.sample.problem


def test_no_leaves_is_unresolved_never_a_side():
    result = resolve_calculated_side([])
    assert result.refusal is None and result.sample.side is None and result.sample.problem == PROBLEM_UNRESOLVED


def test_agreeing_leaves_with_different_authorities_are_labelled_mixed_authority():
    result = resolve_calculated_side([strict(SIDE_PRIMARY, "recording_channel_declared"), strict(SIDE_PRIMARY, "engineer_recording_correction")])
    assert result.sample.side == SIDE_PRIMARY and result.sample.authority == "mixed"
    assert resolve_calculated_side([strict(SIDE_PRIMARY, "x")] * 2).sample.authority == "x"
