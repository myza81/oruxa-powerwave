"""Tests for find_three_phase_vi_sets() (Phase E-1, DEC-208).

Covers 19 scenarios from the approved E-1 specification:
 T01  Complete RYB set with context hint
 T02  Complete ABC set
 T03  Complete L123 set
 T04  Complete L123 with extra B pair — B stays in single_phase_pairs only
 T05  Null-context complete RYB set (DEC-206: exclusion applies to candidates only)
 T06  Incomplete RYB: 2 of 3 automatic pairs (missing_phases / not_found)
 T07  Incomplete ABC: 1 of 3 automatic pairs
 T08  Missing phase has source-specific candidate → needs_confirmation
 T09  B-only pair → no exclusive token → ambiguous_convention
 T10  Mixed RYB+ABC ({R,Y,B,A}) → ambiguous_convention (A blocks RYB)
 T11  Mixed RYB+L123 ({R,Y,B,L1}) → ambiguous_convention
 T12  Two separate bays, each with a complete ABC set
 T13  Two sources at different contexts, each with a complete RYB set
 T14  VR/VY/VB voltage names → voltage_reference = LINE_TO_GROUND
 T15  VL1/VL2/VL3 voltage names → voltage_reference = None, REASON_NO_PATTERN
 T16  single_phase_pairs field is the unmodified VIPairResolution
 T17  Deterministic sort order for multiple complete sets
 T18  Empty workspace
 T19  Source-specific candidate regression: candidate from S2 not matched to S1 group

Pure domain tests — no I/O, no registry, no service layer.
"""

from __future__ import annotations

import pytest

from app.domain.vi_pair_resolution import (
    THREE_PHASE_CONV_ABC,
    THREE_PHASE_CONV_L123,
    THREE_PHASE_CONV_RYB,
    INCOMPLETE_REASON_AMBIGUOUS_CONVENTION,
    INCOMPLETE_REASON_MISSING_PHASES,
    INCOMPLETE_REASON_PHASES_NEED_CONFIRM,
    MISSING_REASON_NEEDS_CONFIRMATION,
    MISSING_REASON_NOT_FOUND,
    ChannelPairingInput,
    ThreePhaseAutomaticSet,
    ThreePhaseIncompleteSet,
    ThreePhaseVISetResolution,
    find_three_phase_vi_sets,
)
from app.domain.voltage_reference import (
    LINE_TO_GROUND,
    REASON_DETECTED,
    REASON_NO_PATTERN,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _ch(
    source_id: str,
    name: str,
    eng_type: str,
    unit: str | None = None,
    phase_label: str | None = None,
) -> ChannelPairingInput:
    return ChannelPairingInput(
        source_id=source_id,
        channel_name=name,
        engineering_type=eng_type,
        unit=unit,
        phase_label=phase_label,
    )


def _ryb_channels(source_id: str, context: str) -> list[ChannelPairingInput]:
    """Six RYB V-I channels with the given context prefix."""
    return [
        _ch(source_id, f"{context} VR", "Voltage"),
        _ch(source_id, f"{context} VY", "Voltage"),
        _ch(source_id, f"{context} VB", "Voltage"),
        _ch(source_id, f"{context} IR", "Current"),
        _ch(source_id, f"{context} IY", "Current"),
        _ch(source_id, f"{context} IB", "Current"),
    ]


def _abc_channels(source_id: str, context: str) -> list[ChannelPairingInput]:
    """Six ABC V-I channels with the given context prefix."""
    return [
        _ch(source_id, f"{context} VA", "Voltage"),
        _ch(source_id, f"{context} VB", "Voltage"),
        _ch(source_id, f"{context} VC", "Voltage"),
        _ch(source_id, f"{context} IA", "Current"),
        _ch(source_id, f"{context} IB", "Current"),
        _ch(source_id, f"{context} IC", "Current"),
    ]


def _l123_channels(source_id: str, context: str) -> list[ChannelPairingInput]:
    """Six L123 V-I channels with the given context prefix."""
    return [
        _ch(source_id, f"{context} VL1", "Voltage"),
        _ch(source_id, f"{context} VL2", "Voltage"),
        _ch(source_id, f"{context} VL3", "Voltage"),
        _ch(source_id, f"{context} IL1", "Current"),
        _ch(source_id, f"{context} IL2", "Current"),
        _ch(source_id, f"{context} IL3", "Current"),
    ]


# ---------------------------------------------------------------------------
# T01: Complete RYB set with context hint
# ---------------------------------------------------------------------------

class TestT01CompleteRYB:
    def test_ryb_complete_set_detected(self):
        channels = _ryb_channels("S1", "IBT1 HV")
        result = find_three_phase_vi_sets(channels)

        assert len(result.complete_sets) == 1
        assert result.incomplete_sets == []
        s = result.complete_sets[0]
        assert s.phase_convention == THREE_PHASE_CONV_RYB
        assert s.source_id == "S1"
        assert s.context_hint == "IBT1 HV"

    def test_ryb_complete_set_phases_are_r_y_b(self):
        channels = _ryb_channels("S1", "IBT1 HV")
        result = find_three_phase_vi_sets(channels)

        s = result.complete_sets[0]
        assert s.phase_1.phase_token == "R"
        assert s.phase_2.phase_token == "Y"
        assert s.phase_3.phase_token == "B"

    def test_ryb_complete_set_id_is_stable(self):
        channels = _ryb_channels("S1", "IBT1 HV")
        result1 = find_three_phase_vi_sets(channels)
        result2 = find_three_phase_vi_sets(channels)

        assert result1.complete_sets[0].set_id == result2.complete_sets[0].set_id
        assert result1.complete_sets[0].set_id.startswith("3ph:")


# ---------------------------------------------------------------------------
# T02: Complete ABC set
# ---------------------------------------------------------------------------

class TestT02CompleteABC:
    def test_abc_complete_set_detected(self):
        channels = _abc_channels("S1", "IBT1 HV")
        result = find_three_phase_vi_sets(channels)

        assert len(result.complete_sets) == 1
        assert result.incomplete_sets == []
        s = result.complete_sets[0]
        assert s.phase_convention == THREE_PHASE_CONV_ABC
        assert s.phase_1.phase_token == "A"
        assert s.phase_2.phase_token == "B"
        assert s.phase_3.phase_token == "C"


# ---------------------------------------------------------------------------
# T03: Complete L123 set
# ---------------------------------------------------------------------------

class TestT03CompleteL123:
    def test_l123_complete_set_detected(self):
        channels = _l123_channels("S1", "IBT1 HV")
        result = find_three_phase_vi_sets(channels)

        assert len(result.complete_sets) == 1
        assert result.incomplete_sets == []
        s = result.complete_sets[0]
        assert s.phase_convention == THREE_PHASE_CONV_L123
        assert s.phase_1.phase_token == "L1"
        assert s.phase_2.phase_token == "L2"
        assert s.phase_3.phase_token == "L3"


# ---------------------------------------------------------------------------
# T04: L123 complete set with extra B pair
# ---------------------------------------------------------------------------

class TestT04L123WithExtraB:
    def test_l123_complete_extracted_b_pair_in_single_phase_only(self):
        channels = _l123_channels("S1", "IBT1 HV") + [
            _ch("S1", "IBT1 HV VB", "Voltage"),
            _ch("S1", "IBT1 HV IB", "Current"),
        ]
        result = find_three_phase_vi_sets(channels)

        assert len(result.complete_sets) == 1
        assert result.complete_sets[0].phase_convention == THREE_PHASE_CONV_L123
        assert result.incomplete_sets == []

    def test_l123_extra_b_pair_present_in_single_phase_pairs(self):
        channels = _l123_channels("S1", "IBT1 HV") + [
            _ch("S1", "IBT1 HV VB", "Voltage"),
            _ch("S1", "IBT1 HV IB", "Current"),
        ]
        result = find_three_phase_vi_sets(channels)

        phase_tokens = {p.phase_token for p in result.single_phase_pairs.automatic_pairs}
        assert "B" in phase_tokens


# ---------------------------------------------------------------------------
# T05: Null-context complete RYB set (DEC-206 compatibility)
# ---------------------------------------------------------------------------

class TestT05NullContextComplete:
    def test_null_context_ryb_automatic_set_detected(self):
        # Plain names without a context prefix → context_hint=None.
        # DEC-206 null-context exclusion applies to CANDIDATES only; complete
        # automatic sets are still detected.
        channels = [
            _ch("S1", "VR", "Voltage"), _ch("S1", "IR", "Current"),
            _ch("S1", "VY", "Voltage"), _ch("S1", "IY", "Current"),
            _ch("S1", "VB", "Voltage"), _ch("S1", "IB", "Current"),
        ]
        result = find_three_phase_vi_sets(channels)

        assert len(result.complete_sets) == 1
        s = result.complete_sets[0]
        assert s.context_hint is None
        assert s.phase_convention == THREE_PHASE_CONV_RYB


# ---------------------------------------------------------------------------
# T06: Incomplete RYB — 2 of 3 present (Y missing, no candidate)
# ---------------------------------------------------------------------------

class TestT06Incomplete2of3:
    def test_ryb_two_of_three_is_incomplete(self):
        channels = [
            _ch("S1", "IBT1 HV VR", "Voltage"), _ch("S1", "IBT1 HV IR", "Current"),
            _ch("S1", "IBT1 HV VB", "Voltage"), _ch("S1", "IBT1 HV IB", "Current"),
        ]
        result = find_three_phase_vi_sets(channels)

        assert result.complete_sets == []
        assert len(result.incomplete_sets) == 1
        inc = result.incomplete_sets[0]
        assert inc.phase_convention == THREE_PHASE_CONV_RYB
        assert inc.incomplete_reason == INCOMPLETE_REASON_MISSING_PHASES

    def test_ryb_two_of_three_missing_phase_is_not_found(self):
        channels = [
            _ch("S1", "IBT1 HV VR", "Voltage"), _ch("S1", "IBT1 HV IR", "Current"),
            _ch("S1", "IBT1 HV VB", "Voltage"), _ch("S1", "IBT1 HV IB", "Current"),
        ]
        result = find_three_phase_vi_sets(channels)

        inc = result.incomplete_sets[0]
        assert len(inc.missing_phases) == 1
        assert inc.missing_phases[0].phase_token == "Y"
        assert inc.missing_phases[0].reason == MISSING_REASON_NOT_FOUND

    def test_ryb_two_of_three_present_pairs_in_output(self):
        channels = [
            _ch("S1", "IBT1 HV VR", "Voltage"), _ch("S1", "IBT1 HV IR", "Current"),
            _ch("S1", "IBT1 HV VB", "Voltage"), _ch("S1", "IBT1 HV IB", "Current"),
        ]
        result = find_three_phase_vi_sets(channels)

        inc = result.incomplete_sets[0]
        present_tokens = {p.phase_token for p in inc.present_pairs}
        assert present_tokens == {"R", "B"}


# ---------------------------------------------------------------------------
# T07: Incomplete ABC — 1 of 3 present (A only)
# ---------------------------------------------------------------------------

class TestT07Incomplete1of3:
    def test_abc_one_of_three_is_incomplete(self):
        channels = [
            _ch("S1", "IBT1 HV VA", "Voltage"),
            _ch("S1", "IBT1 HV IA", "Current"),
        ]
        result = find_three_phase_vi_sets(channels)

        assert result.complete_sets == []
        assert len(result.incomplete_sets) == 1
        inc = result.incomplete_sets[0]
        assert inc.phase_convention == THREE_PHASE_CONV_ABC
        assert inc.incomplete_reason == INCOMPLETE_REASON_MISSING_PHASES

    def test_abc_one_of_three_two_missing_phases_not_found(self):
        channels = [
            _ch("S1", "IBT1 HV VA", "Voltage"),
            _ch("S1", "IBT1 HV IA", "Current"),
        ]
        result = find_three_phase_vi_sets(channels)

        inc = result.incomplete_sets[0]
        missing_tokens = {mp.phase_token for mp in inc.missing_phases}
        assert missing_tokens == {"B", "C"}
        for mp in inc.missing_phases:
            assert mp.reason == MISSING_REASON_NOT_FOUND


# ---------------------------------------------------------------------------
# T08: Missing phase with source-specific candidate → needs_confirmation
# ---------------------------------------------------------------------------

class TestT08MissingPhaseWithCandidate:
    def test_missing_y_with_source_candidate_yields_needs_confirmation(self):
        # Y has two voltage channels at S1 (MULTIPLE_VOLTAGE candidate).
        # The candidate's refs belong to S1 → needs_confirmation for the S1 group.
        channels = [
            _ch("S1", "IBT1 HV VR", "Voltage"), _ch("S1", "IBT1 HV IR", "Current"),
            _ch("S1", "IBT1 HV VB", "Voltage"), _ch("S1", "IBT1 HV IB", "Current"),
            # Two Y voltages at S1 → MULTIPLE_VOLTAGE candidate for Y
            _ch("S1", "IBT1 HV VY", "Voltage"),
            _ch("S1", "IBT1 HV VYN", "Voltage"),
            _ch("S1", "IBT1 HV IY", "Current"),
        ]
        result = find_three_phase_vi_sets(channels)

        assert result.complete_sets == []
        assert len(result.incomplete_sets) == 1
        inc = result.incomplete_sets[0]
        assert inc.incomplete_reason == INCOMPLETE_REASON_PHASES_NEED_CONFIRM
        assert len(inc.missing_phases) == 1
        assert inc.missing_phases[0].phase_token == "Y"
        assert inc.missing_phases[0].reason == MISSING_REASON_NEEDS_CONFIRMATION


# ---------------------------------------------------------------------------
# T09: B-only pair → no exclusive token → ambiguous_convention
# ---------------------------------------------------------------------------

class TestT09BOnlyAmbiguous:
    def test_b_only_pair_is_ambiguous_convention(self):
        # B is shared between RYB and ABC — no exclusive token present.
        channels = [
            _ch("S1", "IBT1 HV VB", "Voltage"),
            _ch("S1", "IBT1 HV IB", "Current"),
        ]
        result = find_three_phase_vi_sets(channels)

        assert result.complete_sets == []
        assert len(result.incomplete_sets) == 1
        inc = result.incomplete_sets[0]
        assert inc.phase_convention is None
        assert inc.incomplete_reason == INCOMPLETE_REASON_AMBIGUOUS_CONVENTION
        assert inc.missing_phases == ()


# ---------------------------------------------------------------------------
# T10: Mixed RYB + ABC → ambiguous (A blocks RYB; R,Y block ABC)
# ---------------------------------------------------------------------------

class TestT10MixedRYBAndABC:
    def test_ryb_plus_abc_tokens_produce_no_complete_set(self):
        channels = [
            _ch("S1", "IBT1 HV VR", "Voltage"), _ch("S1", "IBT1 HV IR", "Current"),
            _ch("S1", "IBT1 HV VY", "Voltage"), _ch("S1", "IBT1 HV IY", "Current"),
            _ch("S1", "IBT1 HV VB", "Voltage"), _ch("S1", "IBT1 HV IB", "Current"),
            _ch("S1", "IBT1 HV VA", "Voltage"), _ch("S1", "IBT1 HV IA", "Current"),
        ]
        result = find_three_phase_vi_sets(channels)

        assert result.complete_sets == []

    def test_ryb_plus_abc_yields_ambiguous_incomplete(self):
        channels = [
            _ch("S1", "IBT1 HV VR", "Voltage"), _ch("S1", "IBT1 HV IR", "Current"),
            _ch("S1", "IBT1 HV VY", "Voltage"), _ch("S1", "IBT1 HV IY", "Current"),
            _ch("S1", "IBT1 HV VB", "Voltage"), _ch("S1", "IBT1 HV IB", "Current"),
            _ch("S1", "IBT1 HV VA", "Voltage"), _ch("S1", "IBT1 HV IA", "Current"),
        ]
        result = find_three_phase_vi_sets(channels)

        assert len(result.incomplete_sets) == 1
        inc = result.incomplete_sets[0]
        assert inc.phase_convention is None
        assert inc.incomplete_reason == INCOMPLETE_REASON_AMBIGUOUS_CONVENTION


# ---------------------------------------------------------------------------
# T11: Mixed RYB + L123 → ambiguous (L1 blocks RYB; R,Y block L123)
# ---------------------------------------------------------------------------

class TestT11MixedRYBAndL123:
    def test_ryb_plus_l123_tokens_produce_no_complete_set(self):
        channels = [
            _ch("S1", "IBT1 HV VR", "Voltage"), _ch("S1", "IBT1 HV IR", "Current"),
            _ch("S1", "IBT1 HV VY", "Voltage"), _ch("S1", "IBT1 HV IY", "Current"),
            _ch("S1", "IBT1 HV VB", "Voltage"), _ch("S1", "IBT1 HV IB", "Current"),
            _ch("S1", "IBT1 HV VL1", "Voltage"), _ch("S1", "IBT1 HV IL1", "Current"),
        ]
        result = find_three_phase_vi_sets(channels)

        assert result.complete_sets == []
        assert len(result.incomplete_sets) == 1
        inc = result.incomplete_sets[0]
        assert inc.phase_convention is None
        assert inc.incomplete_reason == INCOMPLETE_REASON_AMBIGUOUS_CONVENTION


# ---------------------------------------------------------------------------
# T12: Two separate bays, each a complete ABC set
# ---------------------------------------------------------------------------

class TestT12TwoBays:
    def test_two_bays_yield_two_complete_sets(self):
        channels = (
            _abc_channels("S1", "IBT1 HV")
            + _abc_channels("S1", "IBT1 LV")
        )
        result = find_three_phase_vi_sets(channels)

        assert len(result.complete_sets) == 2
        assert result.incomplete_sets == []
        contexts = {s.context_hint for s in result.complete_sets}
        assert contexts == {"IBT1 HV", "IBT1 LV"}

    def test_two_bays_both_abc_convention(self):
        channels = (
            _abc_channels("S1", "IBT1 HV")
            + _abc_channels("S1", "IBT1 LV")
        )
        result = find_three_phase_vi_sets(channels)

        for s in result.complete_sets:
            assert s.phase_convention == THREE_PHASE_CONV_ABC


# ---------------------------------------------------------------------------
# T13: Two sources at different contexts, each a complete RYB set
# ---------------------------------------------------------------------------

class TestT13TwoSources:
    def test_two_sources_yield_two_complete_sets(self):
        channels = (
            _ryb_channels("S1", "IBT1 HV")
            + _ryb_channels("S2", "IBT1 LV")
        )
        result = find_three_phase_vi_sets(channels)

        assert len(result.complete_sets) == 2
        source_ids = {s.source_id for s in result.complete_sets}
        assert source_ids == {"S1", "S2"}

    def test_two_sources_have_distinct_set_ids(self):
        channels = (
            _ryb_channels("S1", "IBT1 HV")
            + _ryb_channels("S2", "IBT1 LV")
        )
        result = find_three_phase_vi_sets(channels)

        set_ids = [s.set_id for s in result.complete_sets]
        assert set_ids[0] != set_ids[1]


# ---------------------------------------------------------------------------
# T14: VR/VY/VB → voltage_reference = LINE_TO_GROUND
# ---------------------------------------------------------------------------

class TestT14VoltageRefLineToGround:
    def test_vr_vy_vb_yield_line_to_ground_reference(self):
        channels = _ryb_channels("S1", "IBT1 HV")
        result = find_three_phase_vi_sets(channels)

        s = result.complete_sets[0]
        assert s.voltage_reference == LINE_TO_GROUND
        assert s.voltage_reference_reason == REASON_DETECTED
        assert len(s.voltage_reference_evidence_names) > 0

    def test_voltage_reference_evidence_names_are_voltage_channels(self):
        channels = _ryb_channels("S1", "IBT1 HV")
        result = find_three_phase_vi_sets(channels)

        s = result.complete_sets[0]
        for name in s.voltage_reference_evidence_names:
            assert name in {"IBT1 HV VR", "IBT1 HV VY", "IBT1 HV VB"}


# ---------------------------------------------------------------------------
# T15: VL1/VL2/VL3 → voltage_reference = None (no recognizable pattern)
# ---------------------------------------------------------------------------

class TestT15VoltageRefNoPattern:
    def test_vl1_vl2_vl3_yield_no_pattern_reference(self):
        # voltage_reference.py only recognizes V-prefixed single/pair/neutral tokens.
        # L1/L2/L3 tokens are not in its detection grammar → REASON_NO_PATTERN.
        channels = _l123_channels("S1", "IBT1 HV")
        result = find_three_phase_vi_sets(channels)

        s = result.complete_sets[0]
        assert s.voltage_reference is None
        assert s.voltage_reference_reason == REASON_NO_PATTERN
        assert s.voltage_reference_evidence_names == ()


# ---------------------------------------------------------------------------
# T16: single_phase_pairs is the unmodified VIPairResolution
# ---------------------------------------------------------------------------

class TestT16SinglePhasePairsUnmodified:
    def test_single_phase_pairs_contains_all_automatic_pairs(self):
        channels = _ryb_channels("S1", "IBT1 HV")
        result = find_three_phase_vi_sets(channels)

        # The three-phase set is found AND single_phase_pairs still has all 3 pairs.
        assert len(result.complete_sets) == 1
        assert len(result.single_phase_pairs.automatic_pairs) == 3

    def test_single_phase_pairs_candidates_unaffected(self):
        # Cross-source candidate (with context) still appears in single_phase_pairs.
        channels = [
            _ch("S1", "IBT1 HV VA", "Voltage"),
            _ch("S2", "IBT1 HV IA", "Current"),   # cross-source → candidate
        ]
        result = find_three_phase_vi_sets(channels)

        assert len(result.single_phase_pairs.candidates_needing_confirmation) == 1


# ---------------------------------------------------------------------------
# T17: Deterministic sort order for multiple complete sets
# ---------------------------------------------------------------------------

class TestT17DeterministicOrdering:
    def test_complete_sets_sorted_by_context_then_source_then_convention(self):
        # Feed channels in reverse alphabetical context order; output must be sorted.
        channels = (
            _ryb_channels("S1", "Z-BAY HV")   # should sort last
            + _ryb_channels("S1", "A-BAY HV")  # should sort first
        )
        result = find_three_phase_vi_sets(channels)

        assert len(result.complete_sets) == 2
        assert result.complete_sets[0].context_hint == "A-BAY HV"
        assert result.complete_sets[1].context_hint == "Z-BAY HV"

    def test_incomplete_sets_are_also_sorted(self):
        channels = [
            _ch("S1", "Z-BAY HV VR", "Voltage"), _ch("S1", "Z-BAY HV IR", "Current"),
            _ch("S1", "A-BAY HV VR", "Voltage"), _ch("S1", "A-BAY HV IR", "Current"),
        ]
        result = find_three_phase_vi_sets(channels)

        assert len(result.incomplete_sets) == 2
        assert result.incomplete_sets[0].context_hint == "A-BAY HV"
        assert result.incomplete_sets[1].context_hint == "Z-BAY HV"


# ---------------------------------------------------------------------------
# T18: Empty workspace
# ---------------------------------------------------------------------------

class TestT18Empty:
    def test_empty_input_returns_empty_resolution(self):
        result = find_three_phase_vi_sets([])

        assert result.complete_sets == []
        assert result.incomplete_sets == []
        assert result.single_phase_pairs.automatic_pairs == []
        assert result.single_phase_pairs.candidates_needing_confirmation == []


# ---------------------------------------------------------------------------
# T19: Source-specific candidate regression
# ---------------------------------------------------------------------------

class TestT19SourceSpecificCandidateRegression:
    def test_candidate_with_s2_refs_only_does_not_match_s1_group(self):
        # S1 has R and B automatic pairs.
        # S2 has two Y voltages (MULTIPLE_VOLTAGE candidate) with refs from S2 only.
        # The S1 group's missing Y should be NOT_FOUND, not NEEDS_CONFIRMATION.
        channels = [
            _ch("S1", "IBT1 HV VR", "Voltage"), _ch("S1", "IBT1 HV IR", "Current"),
            _ch("S1", "IBT1 HV VB", "Voltage"), _ch("S1", "IBT1 HV IB", "Current"),
            # S2 Y candidate — refs are all S2
            _ch("S2", "IBT1 HV VY", "Voltage"),
            _ch("S2", "IBT1 HV VYN", "Voltage"),
            _ch("S2", "IBT1 HV IY", "Current"),
        ]
        result = find_three_phase_vi_sets(channels)

        assert result.complete_sets == []
        # Find the S1 incomplete set
        s1_inc = next(
            (inc for inc in result.incomplete_sets if inc.source_id == "S1"),
            None,
        )
        assert s1_inc is not None
        assert len(s1_inc.missing_phases) == 1
        assert s1_inc.missing_phases[0].phase_token == "Y"
        assert s1_inc.missing_phases[0].reason == MISSING_REASON_NOT_FOUND

    def test_cross_source_candidate_s1_voltage_s2_current_not_found_for_s1(self):
        # S1 has Phase Y voltage only; S2 has Phase Y current only.
        # The cross-source candidate has voltage_refs=(S1/VY,), current_refs=(S2/IY).
        # S1 has no same-source Y current → the AND check yields NOT_FOUND for S1.
        channels = [
            _ch("S1", "IBT1 HV VR", "Voltage"), _ch("S1", "IBT1 HV IR", "Current"),
            _ch("S1", "IBT1 HV VB", "Voltage"), _ch("S1", "IBT1 HV IB", "Current"),
            _ch("S1", "IBT1 HV VY", "Voltage"),   # S1 Y voltage only
            _ch("S2", "IBT1 HV IY", "Current"),   # S2 Y current only → cross-source candidate
        ]
        result = find_three_phase_vi_sets(channels)

        s1_inc = next(
            (inc for inc in result.incomplete_sets if inc.source_id == "S1"),
            None,
        )
        assert s1_inc is not None
        missing_y = next(
            (mp for mp in s1_inc.missing_phases if mp.phase_token == "Y"),
            None,
        )
        assert missing_y is not None
        assert missing_y.reason == MISSING_REASON_NOT_FOUND
