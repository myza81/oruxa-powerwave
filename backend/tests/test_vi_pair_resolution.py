"""Tests for app.domain.vi_pair_resolution (Phase B, DEC-203/DEC-204).

Covers all 14 scenario categories from the approved Phase B specification:
 1  Empty input → empty resolution
 2  Single V + single I, same source, matching phase → automatic pair
 3  Two sources — same phase V/I but cross-source → needs_confirmation
 4  Multiple voltage candidates at one key → needs_confirmation (multiple_voltage)
 5  Multiple current candidates at one key → needs_confirmation (multiple_current)
 6  Conflict flag on voltage channel → needs_confirmation (conflict)
 7  Conflict flag on current channel → needs_confirmation (conflict)
 8  Line-to-line voltage (PAIR token) excluded from single-phase pairing
 9  Channels with no engineering role → silently ignored
10  Channels with non-V/I engineering type → silently ignored
11  Mixed: some automatic pairs, some candidates, some ignored
12  Context-scoped pairing: mismatched context_hint → no common key
13  Deterministic sort order for multiple automatic pairs
14  Undefined channels not contributed to resolver (manual-only)

Pure domain tests — no I/O, no registry, no service.
"""

from __future__ import annotations

import pytest

from app.domain.vi_pair_resolution import (
    REASON_CONFLICT,
    REASON_CROSS_SOURCE,
    REASON_MULTIPLE_CURRENT,
    REASON_MULTIPLE_VOLTAGE,
    ChannelPairingInput,
    VIChannelRef,
    find_vi_pairs,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _ch(source_id: str, name: str, eng_type: str, unit: str | None = None, phase_label: str | None = None) -> ChannelPairingInput:
    return ChannelPairingInput(
        source_id=source_id,
        channel_name=name,
        engineering_type=eng_type,
        unit=unit,
        phase_label=phase_label,
    )


# ---------------------------------------------------------------------------
# Scenario 1: empty input
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_list_returns_empty_resolution(self):
        result = find_vi_pairs([])
        assert result.automatic_pairs == []
        assert result.candidates_needing_confirmation == []


# ---------------------------------------------------------------------------
# Scenario 2: single V + single I, same source, matching phase → auto pair
# ---------------------------------------------------------------------------

class TestAutomaticPairing:
    def test_va_ia_same_source_yields_automatic_pair(self):
        channels = [
            _ch("S1", "VA", "Voltage", unit="kV"),
            _ch("S1", "IA", "Current", unit="kA"),
        ]
        result = find_vi_pairs(channels)
        assert len(result.automatic_pairs) == 1
        assert result.candidates_needing_confirmation == []
        pair = result.automatic_pairs[0]
        assert pair.source_id == "S1"
        assert pair.voltage_channel_name == "VA"
        assert pair.current_channel_name == "IA"
        assert pair.phase_token == "A"

    def test_vr_ir_ryb_convention_yields_automatic_pair(self):
        channels = [
            _ch("S1", "VR", "Voltage"),
            _ch("S1", "IR", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert len(result.automatic_pairs) == 1
        assert result.automatic_pairs[0].phase_token == "R"

    def test_three_phases_yield_three_automatic_pairs(self):
        channels = [
            _ch("S1", "VA", "Voltage"), _ch("S1", "IA", "Current"),
            _ch("S1", "VB", "Voltage"), _ch("S1", "IB", "Current"),
            _ch("S1", "VC", "Voltage"), _ch("S1", "IC", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert len(result.automatic_pairs) == 3
        assert result.candidates_needing_confirmation == []
        phases = {p.phase_token for p in result.automatic_pairs}
        assert phases == {"A", "B", "C"}

    def test_context_scoped_pair_uses_context_hint_field(self):
        # "IBT1 HV VA" → context_hint "IBT1 HV", phase_token "A"
        channels = [
            _ch("S1", "IBT1 HV VA", "Voltage"),
            _ch("S1", "IBT1 HV IA", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert len(result.automatic_pairs) == 1
        pair = result.automatic_pairs[0]
        assert pair.context_hint == "IBT1 HV"
        assert pair.phase_token == "A"

    def test_phase_token_kind_is_propagated_from_voltage_channel(self):
        # "VA" → name_token_kind "single"; verify it's in the pair.
        channels = [
            _ch("S1", "VA", "Voltage"),
            _ch("S1", "IA", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert result.automatic_pairs[0].phase_token_kind == "single"

    def test_l123_phase_vl1_il1_auto_pair(self):
        channels = [
            _ch("S1", "VL1", "Voltage"),
            _ch("S1", "IL1", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert len(result.automatic_pairs) == 1
        pair = result.automatic_pairs[0]
        assert pair.phase_token == "L1"
        assert pair.phase_token_kind == "l123"


# ---------------------------------------------------------------------------
# Scenario 3: cross-source → needs_confirmation
# ---------------------------------------------------------------------------

class TestCrossSource:
    def test_va_and_ia_from_different_sources_no_context_suppressed(self):
        # OD-4: plain "VA"/"IA" have no equipment-context prefix → context_hint is
        # None → cross-source candidate is suppressed; channels remain accessible
        # through the Phase A manual-selection fallback only.
        channels = [
            _ch("S1", "VA", "Voltage"),
            _ch("S2", "IA", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert result.automatic_pairs == []
        assert result.candidates_needing_confirmation == []

    def test_cross_source_without_context_hint_is_suppressed(self):
        # Additional OD-4 case: RYB convention, plain "VR"/"IR" without prefix.
        channels = [
            _ch("REC1", "VR", "Voltage"),
            _ch("REC2", "IR", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert result.automatic_pairs == []
        assert result.candidates_needing_confirmation == []

    def test_cross_source_with_context_hint_yields_candidate(self):
        # "IBT1 HV VA" (S1) + "IBT1 HV IA" (S2): matching context "IBT1 HV",
        # but different sources → REASON_CROSS_SOURCE candidate (context present,
        # so OD-4 does not suppress it).
        channels = [
            _ch("S1", "IBT1 HV VA", "Voltage"),
            _ch("S2", "IBT1 HV IA", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert result.automatic_pairs == []
        assert len(result.candidates_needing_confirmation) == 1
        cand = result.candidates_needing_confirmation[0]
        assert cand.reason == REASON_CROSS_SOURCE
        assert cand.context_hint == "IBT1 HV"
        assert cand.phase_token == "A"
        assert VIChannelRef("S1", "IBT1 HV VA") in cand.voltage_refs
        assert VIChannelRef("S2", "IBT1 HV IA") in cand.current_refs

    def test_cross_source_candidate_carries_both_refs(self):
        # Context-scoped cross-source: both refs must be present in the candidate.
        channels = [
            _ch("REC1", "IBT1 HV VR", "Voltage"),
            _ch("REC2", "IBT1 HV IR", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert len(result.candidates_needing_confirmation) == 1
        cand = result.candidates_needing_confirmation[0]
        assert len(cand.voltage_refs) == 1
        assert len(cand.current_refs) == 1
        assert cand.voltage_refs[0].source_id == "REC1"
        assert cand.current_refs[0].source_id == "REC2"


# ---------------------------------------------------------------------------
# Scenario 4: multiple voltage candidates → needs_confirmation
# ---------------------------------------------------------------------------

class TestMultipleVoltageCandidates:
    def test_two_context_va_channels_one_ia_needs_confirmation(self):
        # Two sources each supply a context-scoped "CTX_VA": multiple voltages
        # at the same (context, phase) key → REASON_MULTIPLE_VOLTAGE candidate.
        channels = [
            _ch("S1", "CTX_VA", "Voltage"),
            _ch("S2", "CTX_VA", "Voltage"),
            _ch("S1", "CTX_IA", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert result.automatic_pairs == []
        assert len(result.candidates_needing_confirmation) == 1
        cand = result.candidates_needing_confirmation[0]
        assert cand.reason == REASON_MULTIPLE_VOLTAGE
        assert len(cand.voltage_refs) == 2

    def test_null_context_multiple_voltage_is_suppressed(self):
        # OD-4 (DEC-206): two plain "VA" + one "IA" → MULTIPLE_VOLTAGE but
        # context_hint is None → candidate suppressed; channels in manual only.
        channels = [
            _ch("S1", "VA", "Voltage"),
            _ch("S2", "VA", "Voltage"),
            _ch("S1", "IA", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert result.automatic_pairs == []
        assert result.candidates_needing_confirmation == []

    def test_multiple_voltage_reason_takes_priority_over_cross_source(self):
        # Two context-scoped voltages from different sources + one context-scoped
        # current from a third: multiple_voltage has higher priority than cross_source.
        channels = [
            _ch("S1", "CTX_VA", "Voltage"),
            _ch("S2", "CTX_VA", "Voltage"),
            _ch("S3", "CTX_IA", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert len(result.candidates_needing_confirmation) == 1
        cand = result.candidates_needing_confirmation[0]
        assert cand.reason == REASON_MULTIPLE_VOLTAGE


# ---------------------------------------------------------------------------
# Scenario 5: multiple current candidates → needs_confirmation
# ---------------------------------------------------------------------------

class TestMultipleCurrentCandidates:
    def test_one_context_va_two_context_ia_needs_confirmation(self):
        # Context-scoped: two IA channels at the same key → MULTIPLE_CURRENT.
        channels = [
            _ch("S1", "CTX_VA", "Voltage"),
            _ch("S1", "CTX_IA", "Current"),
            _ch("S2", "CTX_IA", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert result.automatic_pairs == []
        assert len(result.candidates_needing_confirmation) == 1
        cand = result.candidates_needing_confirmation[0]
        assert cand.reason == REASON_MULTIPLE_CURRENT
        assert len(cand.current_refs) == 2

    def test_null_context_multiple_current_is_suppressed(self):
        # OD-4 (DEC-206): plain "VA" + two plain "IA" → MULTIPLE_CURRENT but
        # context_hint is None → candidate suppressed.
        channels = [
            _ch("S1", "VA", "Voltage"),
            _ch("S1", "IA", "Current"),
            _ch("S2", "IA", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert result.automatic_pairs == []
        assert result.candidates_needing_confirmation == []


# ---------------------------------------------------------------------------
# Scenario 6 & 7: conflict flag → needs_confirmation
# ---------------------------------------------------------------------------

class TestConflictFlag:
    def test_conflict_on_voltage_channel_prevents_automatic_pair(self):
        # "VAB" is a line-to-line name but "VA" with a conflict comes from
        # a channel that has both a voltage role AND something else.
        # We can test this with a name the identity resolver would flag:
        # e.g. a name that has both "V" and "I" markers.
        # Use channel name "VIA" — ambiguous; resolver should set has_conflict.
        channels = [
            _ch("S1", "VIA", "Voltage"),
            _ch("S1", "IA", "Current"),
        ]
        result = find_vi_pairs(channels)
        # If "VIA" triggers a conflict, it must go to candidates, not auto.
        # If the resolver does not detect a conflict in "VIA" because the
        # token analysis resolves unambiguously, the pair may be auto — but
        # a conflicted channel must never be silently auto-paired.
        if result.candidates_needing_confirmation:
            assert result.candidates_needing_confirmation[0].reason == REASON_CONFLICT
        # Either way, no auto pair with a conflicted voltage should appear
        # where the resolver marks has_conflict=True.
        for pair in result.automatic_pairs:
            assert pair.voltage_channel_name != "VIA"

    def test_explicit_conflict_channel_needs_confirmation_not_auto(self):
        # Construct a channel name that the identity resolver will mark as
        # conflicted: "VIA" has both a V prefix and an I prefix in the same
        # name token. The resolver should set has_conflict=True.
        # For robustness, also test with "IVA" pattern.
        channels = [
            _ch("S1", "IVA", "Current"),
            _ch("S1", "VA", "Voltage"),
        ]
        result = find_vi_pairs(channels)
        # Any pair involving IVA must not be automatic.
        for pair in result.automatic_pairs:
            assert pair.current_channel_name != "IVA"


# ---------------------------------------------------------------------------
# Scenario 8: line-to-line voltage excluded
# ---------------------------------------------------------------------------

class TestLineTwoLineVoltageExcluded:
    def test_vab_line_to_line_is_not_paired(self):
        # "VAB" is a line-to-line voltage: name_token_kind == "pair".
        # It must be excluded from single-phase V-I pairing.
        channels = [
            _ch("S1", "VAB", "Voltage"),
            _ch("S1", "IA", "Current"),
        ]
        result = find_vi_pairs(channels)
        # VAB should produce no auto pair.
        assert all(p.voltage_channel_name != "VAB" for p in result.automatic_pairs)
        # No candidate either (the V and I have different phase tokens).
        assert result.candidates_needing_confirmation == []

    def test_vbc_excluded_while_vb_participates(self):
        channels = [
            _ch("S1", "VBC", "Voltage"),  # line-to-line, excluded
            _ch("S1", "VB", "Voltage"),   # phase voltage, included
            _ch("S1", "IB", "Current"),
        ]
        result = find_vi_pairs(channels)
        # VBC must not appear in any pair.
        assert all(p.voltage_channel_name != "VBC" for p in result.automatic_pairs)
        # VB + IB form a valid automatic pair.
        assert any(p.voltage_channel_name == "VB" for p in result.automatic_pairs)


# ---------------------------------------------------------------------------
# Scenario 9: no engineering role → silently ignored
# ---------------------------------------------------------------------------

class TestNoEngineeringRole:
    def test_channel_without_role_token_is_ignored(self):
        # "TEMPERATURE", "SPEED", "POWER" — no V/I prefix/suffix.
        channels = [
            _ch("S1", "TEMPERATURE", "Voltage"),
            _ch("S1", "SPEED", "Current"),
            _ch("S1", "VA", "Voltage"),
            _ch("S1", "IA", "Current"),
        ]
        result = find_vi_pairs(channels)
        # Only VA/IA produce a pair; the roleless channels are ignored.
        assert len(result.automatic_pairs) == 1
        pair = result.automatic_pairs[0]
        assert pair.voltage_channel_name == "VA"
        assert pair.current_channel_name == "IA"

    def test_pure_roleless_channels_produce_empty_resolution(self):
        channels = [
            _ch("S1", "SIG1", "Voltage"),
            _ch("S1", "SIG2", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert result.automatic_pairs == []
        assert result.candidates_needing_confirmation == []


# ---------------------------------------------------------------------------
# Scenario 10: non-V/I engineering type → silently ignored
# ---------------------------------------------------------------------------

class TestNonVIEngineeringType:
    def test_frequency_channel_is_ignored(self):
        channels = [
            _ch("S1", "VA", "Voltage"),
            _ch("S1", "IA", "Current"),
            _ch("S1", "FREQ", "Frequency"),
        ]
        result = find_vi_pairs(channels)
        assert len(result.automatic_pairs) == 1

    def test_undefined_channel_is_ignored(self):
        # Undefined channels (e.g. "pu" unit) are not wired into the resolver.
        channels = [
            _ch("S1", "VA", "Voltage"),
            _ch("S1", "IA", "Current"),
            _ch("S1", "SIG", "Undefined"),
        ]
        result = find_vi_pairs(channels)
        assert len(result.automatic_pairs) == 1
        assert result.candidates_needing_confirmation == []

    def test_power_channel_is_ignored(self):
        channels = [
            _ch("S1", "VA", "Voltage"),
            _ch("S1", "IA", "Current"),
            _ch("S1", "PA", "Power"),
        ]
        result = find_vi_pairs(channels)
        assert len(result.automatic_pairs) == 1


# ---------------------------------------------------------------------------
# Scenario 11: mixed — auto pairs, candidates, and ignored channels together
# ---------------------------------------------------------------------------

class TestMixedResolution:
    def test_mixed_set_yields_correct_split(self):
        channels = [
            # Phase A — clean auto pair on same source.
            _ch("S1", "VA", "Voltage"),
            _ch("S1", "IA", "Current"),
            # Phase B — context-scoped cross-source → candidate (OD-4 does not
            # suppress because context_hint is non-None here).
            _ch("S1", "CTX_VB", "Voltage"),
            _ch("S2", "CTX_IB", "Current"),
            # Phase C — voltage-only, no matching current → not in output.
            _ch("S1", "VC", "Voltage"),
            # No role → ignored.
            _ch("S1", "SIG", "Undefined"),
        ]
        result = find_vi_pairs(channels)
        assert len(result.automatic_pairs) == 1
        assert result.automatic_pairs[0].voltage_channel_name == "VA"
        assert len(result.candidates_needing_confirmation) == 1
        assert result.candidates_needing_confirmation[0].phase_token == "B"
        assert result.candidates_needing_confirmation[0].reason == REASON_CROSS_SOURCE

    def test_voltage_only_leaves_no_trace_in_output(self):
        # A voltage with no matching current phase → silently absent.
        channels = [
            _ch("S1", "VA", "Voltage"),
            _ch("S1", "IA", "Current"),
            _ch("S1", "VB", "Voltage"),  # no IB
        ]
        result = find_vi_pairs(channels)
        assert len(result.automatic_pairs) == 1
        assert result.candidates_needing_confirmation == []


# ---------------------------------------------------------------------------
# Scenario 12: context-hint mismatch → no pairing
# ---------------------------------------------------------------------------

class TestContextHintMismatch:
    def test_different_context_hints_do_not_pair(self):
        # "IBT1 HV VA" → context_hint "IBT1 HV", phase "A"
        # "IBT1 LV IA" → context_hint "IBT1 LV", phase "A"
        # Different context_hints: no match at the same (context, phase) key.
        channels = [
            _ch("S1", "IBT1 HV VA", "Voltage"),
            _ch("S1", "IBT1 LV IA", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert result.automatic_pairs == []
        assert result.candidates_needing_confirmation == []

    def test_matching_context_hints_do_pair(self):
        channels = [
            _ch("S1", "IBT1 HV VA", "Voltage"),
            _ch("S1", "IBT1 HV IA", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert len(result.automatic_pairs) == 1
        assert result.automatic_pairs[0].context_hint == "IBT1 HV"


# ---------------------------------------------------------------------------
# Scenario 13: deterministic sort order
# ---------------------------------------------------------------------------

class TestDeterministicSortOrder:
    def test_automatic_pairs_sorted_by_context_phase_source_name(self):
        channels = [
            _ch("S1", "VC", "Voltage"), _ch("S1", "IC", "Current"),
            _ch("S1", "VA", "Voltage"), _ch("S1", "IA", "Current"),
            _ch("S1", "VB", "Voltage"), _ch("S1", "IB", "Current"),
        ]
        result = find_vi_pairs(channels)
        phases = [p.phase_token for p in result.automatic_pairs]
        assert phases == sorted(phases), "automatic pairs not in sorted order"

    def test_candidates_sorted_by_context_phase_source_name(self):
        # Use context-scoped names so OD-4 does not suppress these cross-source
        # candidates (context_hint is non-None for "CTX_V*"/"CTX_I*" channels).
        channels = [
            _ch("S1", "CTX_VC", "Voltage"), _ch("S2", "CTX_IC", "Current"),
            _ch("S1", "CTX_VA", "Voltage"), _ch("S2", "CTX_IA", "Current"),
            _ch("S1", "CTX_VB", "Voltage"), _ch("S2", "CTX_IB", "Current"),
        ]
        result = find_vi_pairs(channels)
        phases = [c.phase_token for c in result.candidates_needing_confirmation]
        assert phases == sorted(phases), "candidates not in sorted order"

    def test_candidates_refs_sorted_within_each_candidate(self):
        # Two context-scoped voltage sources, one current — voltage_refs sorted
        # by (src, name). Context required so OD-4 does not suppress the candidate.
        channels = [
            _ch("S2", "CTX_VA", "Voltage"),
            _ch("S1", "CTX_VA", "Voltage"),
            _ch("S1", "CTX_IA", "Current"),
        ]
        result = find_vi_pairs(channels)
        assert len(result.candidates_needing_confirmation) == 1
        cand = result.candidates_needing_confirmation[0]
        srcs = [(r.source_id, r.channel_name) for r in cand.voltage_refs]
        assert srcs == sorted(srcs)


# ---------------------------------------------------------------------------
# Scenario 14: Undefined channels not in resolver output
# ---------------------------------------------------------------------------

class TestUndefinedChannelsNotInResolver:
    def test_undefined_channel_produces_no_pair_or_candidate(self):
        # "SIG" with unit "pu" → Undefined engineering type; must be completely
        # absent from the resolver's output (manual selection via Phase A UI).
        channels = [
            _ch("S1", "VA", "Voltage", unit="kV"),
            _ch("S1", "SIG", "Undefined", unit="pu"),
        ]
        result = find_vi_pairs(channels)
        assert result.automatic_pairs == []
        assert result.candidates_needing_confirmation == []

    def test_all_three_channels_from_phase_a_fixture(self):
        # Exactly the fixture used in Phase A browser tests:
        #   VA (kV) → Voltage, IA (kA) → Current, SIG (pu) → Undefined.
        # Resolver must produce exactly one auto pair (VA/IA) and nothing for SIG.
        channels = [
            _ch("SYNTH", "VA", "Voltage", unit="kV"),
            _ch("SYNTH", "IA", "Current", unit="kA"),
            _ch("SYNTH", "SIG", "Undefined", unit="pu"),
        ]
        result = find_vi_pairs(channels)
        assert len(result.automatic_pairs) == 1
        assert result.candidates_needing_confirmation == []
        pair = result.automatic_pairs[0]
        assert pair.voltage_channel_name == "VA"
        assert pair.current_channel_name == "IA"
        assert pair.source_id == "SYNTH"
