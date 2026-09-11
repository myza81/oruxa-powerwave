"""Tests for app.domain.engineering_context_detection (Analysis Guardrail
Slice 1): the pure, deterministic cross-kind bay-clustering algorithm --
no registry, no service, no I/O. Covers the owner's own explicit test
matrix: complete bay, multiple bays, single phase, duplicate, wrong
engineering type, structured phase metadata, unknown phase.
"""

from __future__ import annotations

from app.domain.channel_classification import CURRENT, POWER, VOLTAGE
from app.domain.engineering_context_detection import ChannelForDetection, detect_engineering_contexts
from app.domain.measurement_group import STATUS_NEEDS_REVIEW, STATUS_SUGGESTED
from app.domain.phase_identity import (
    PHASE_A,
    PHASE_B,
    PHASE_C,
    PHASE_SOURCE_DETECTED_FROM_NAME,
    PHASE_SOURCE_STRUCTURED_METADATA,
    PHASE_UNKNOWN,
)


def _by_display_name(detected, name):
    return next(d for d in detected if d.display_name == name)


def _phase_by_channel(detected_context, channel_name):
    return next(m.phase for m in detected_context.members if m.channel_name == channel_name)


class TestCompleteBay:
    def test_alpha1_full_six_channel_bay(self):
        channels = [
            ChannelForDetection("ALPHA1_VA", VOLTAGE),
            ChannelForDetection("ALPHA1_VB", VOLTAGE),
            ChannelForDetection("ALPHA1_VC", VOLTAGE),
            ChannelForDetection("ALPHA1_IA", CURRENT),
            ChannelForDetection("ALPHA1_IB", CURRENT),
            ChannelForDetection("ALPHA1_IC", CURRENT),
        ]
        detected = detect_engineering_contexts(channels)
        assert len(detected) == 1
        context = detected[0]
        assert context.display_name == "ALPHA1"
        assert context.status == STATUS_SUGGESTED
        assert {m.channel_name for m in context.members} == {
            "ALPHA1_VA", "ALPHA1_VB", "ALPHA1_VC", "ALPHA1_IA", "ALPHA1_IB", "ALPHA1_IC",
        }
        assert _phase_by_channel(context, "ALPHA1_VA") == PHASE_A
        assert _phase_by_channel(context, "ALPHA1_VB") == PHASE_B
        assert _phase_by_channel(context, "ALPHA1_VC") == PHASE_C
        assert _phase_by_channel(context, "ALPHA1_IA") == PHASE_A
        # Cross-kind clustering: Voltage and Current end up in ONE
        # context, unlike measurement_group_detection's own (base_name,
        # kind)-keyed clustering.
        for m in context.members:
            assert m.phase_source == PHASE_SOURCE_DETECTED_FROM_NAME


class TestMultipleBaysInOneSource:
    def test_three_separate_bays_not_merged(self):
        channels = [
            ChannelForDetection("ALPHA1_VA", VOLTAGE), ChannelForDetection("ALPHA1_VB", VOLTAGE),
            ChannelForDetection("ALPHA1_VC", VOLTAGE), ChannelForDetection("ALPHA1_IA", CURRENT),
            ChannelForDetection("ALPHA2_VA", VOLTAGE), ChannelForDetection("ALPHA2_IA", CURRENT),
            ChannelForDetection("BRAVO1_VA", VOLTAGE), ChannelForDetection("BRAVO1_IA", CURRENT),
        ]
        detected = detect_engineering_contexts(channels)
        names = {d.display_name for d in detected}
        assert names == {"ALPHA1", "ALPHA2", "BRAVO1"}
        alpha1 = _by_display_name(detected, "ALPHA1")
        alpha2 = _by_display_name(detected, "ALPHA2")
        bravo1 = _by_display_name(detected, "BRAVO1")
        alpha1_names = {m.channel_name for m in alpha1.members}
        alpha2_names = {m.channel_name for m in alpha2.members}
        bravo1_names = {m.channel_name for m in bravo1.members}
        # Never merged despite sharing prefixes/letters.
        assert not (alpha1_names & alpha2_names)
        assert not (alpha1_names & bravo1_names)
        assert not (alpha2_names & bravo1_names)


class TestSinglePhaseIsLegitimate:
    def test_single_phase_va_ia_context_not_rejected_for_incompleteness(self):
        channels = [ChannelForDetection("ALPHA1_VA", VOLTAGE), ChannelForDetection("ALPHA1_IA", CURRENT)]
        detected = detect_engineering_contexts(channels)
        assert len(detected) == 1
        context = detected[0]
        assert context.status == STATUS_SUGGESTED
        assert len(context.members) == 2


class TestDuplicateRoleGuardrail:
    def test_two_members_resolving_to_same_voltage_phase_a_is_needs_review(self):
        """"ALPHA1_VA" (single-suffix) and "ALPHA1_VAN" (neutral-suffix)
        both resolve to canonical Voltage Phase A within the same root --
        a real-world plausible duplicate/mislabeling scenario. Detection
        must flag this, never silently pick one."""
        channels = [
            ChannelForDetection("ALPHA1_VA", VOLTAGE),
            ChannelForDetection("ALPHA1_VAN", VOLTAGE),
            ChannelForDetection("ALPHA1_IA", CURRENT),
        ]
        detected = detect_engineering_contexts(channels)
        assert len(detected) == 1
        context = detected[0]
        assert context.status == STATUS_NEEDS_REVIEW
        # The context still exists, with all evidence, never silently
        # dropping one of the ambiguous candidates.
        assert {m.channel_name for m in context.members} == {"ALPHA1_VA", "ALPHA1_VAN", "ALPHA1_IA"}


class TestWrongEngineeringTypeExcluded:
    def test_power_channel_never_becomes_voltage_or_current(self):
        channels = [
            ChannelForDetection("ALPHA1_VA", VOLTAGE),
            ChannelForDetection("ALPHA1_IA", CURRENT),
            ChannelForDetection("ALPHA1_MW", POWER),
        ]
        detected = detect_engineering_contexts(channels)
        assert len(detected) == 1
        context = detected[0]
        names = {m.channel_name for m in context.members}
        assert "ALPHA1_MW" not in names
        assert names == {"ALPHA1_VA", "ALPHA1_IA"}


class TestRootlessBareRoleFallback:
    def test_complete_bare_abc_source_creates_default_context(self):
        channels = [
            ChannelForDetection("VA", VOLTAGE, phase_label="A"),
            ChannelForDetection("VB", VOLTAGE, phase_label="B"),
            ChannelForDetection("VC", VOLTAGE, phase_label="C"),
            ChannelForDetection("IA", CURRENT, phase_label="A"),
            ChannelForDetection("IB", CURRENT, phase_label="B"),
            ChannelForDetection("IC", CURRENT, phase_label="C"),
        ]
        detected = detect_engineering_contexts(channels)
        assert len(detected) == 1
        context = detected[0]
        assert context.display_name == "Default Context"
        assert context.status == STATUS_SUGGESTED
        assert {m.channel_name for m in context.members} == {"VA", "VB", "VC", "IA", "IB", "IC"}
        assert _phase_by_channel(context, "VA") == PHASE_A
        assert _phase_by_channel(context, "VB") == PHASE_B
        assert _phase_by_channel(context, "VC") == PHASE_C
        assert _phase_by_channel(context, "IA") == PHASE_A
        for m in context.members:
            assert m.phase_source == PHASE_SOURCE_STRUCTURED_METADATA

    def test_partial_bare_va_ia_context_is_allowed(self):
        channels = [ChannelForDetection("VA", VOLTAGE), ChannelForDetection("IA", CURRENT)]
        detected = detect_engineering_contexts(channels)
        assert len(detected) == 1
        context = detected[0]
        assert context.display_name == "Default Context"
        assert context.status == STATUS_SUGGESTED
        assert {m.channel_name for m in context.members} == {"VA", "IA"}
        assert _phase_by_channel(context, "VA") == PHASE_A
        assert _phase_by_channel(context, "IA") == PHASE_A

    def test_bare_ryb_roles_normalize_under_ryb_convention(self):
        channels = [
            ChannelForDetection("VR", VOLTAGE),
            ChannelForDetection("VY", VOLTAGE),
            ChannelForDetection("VB", VOLTAGE),
            ChannelForDetection("IR", CURRENT),
            ChannelForDetection("IY", CURRENT),
            ChannelForDetection("IB", CURRENT),
        ]
        detected = detect_engineering_contexts(channels)
        assert len(detected) == 1
        context = detected[0]
        assert context.display_name == "Default Context"
        assert context.status == STATUS_SUGGESTED
        assert _phase_by_channel(context, "VR") == PHASE_A
        assert _phase_by_channel(context, "VY") == PHASE_B
        assert _phase_by_channel(context, "VB") == PHASE_C
        assert _phase_by_channel(context, "IR") == PHASE_A
        assert _phase_by_channel(context, "IY") == PHASE_B
        assert _phase_by_channel(context, "IB") == PHASE_C
        for m in context.members:
            assert m.phase_source == PHASE_SOURCE_DETECTED_FROM_NAME

    def test_duplicate_bare_role_is_needs_review_not_silently_chosen(self):
        channels = [
            ChannelForDetection("VA", VOLTAGE),
            ChannelForDetection("VAN", VOLTAGE),
            ChannelForDetection("IA", CURRENT),
        ]
        detected = detect_engineering_contexts(channels)
        assert len(detected) == 1
        context = detected[0]
        assert context.status == STATUS_NEEDS_REVIEW
        assert {m.channel_name for m in context.members} == {"VA", "VAN", "IA"}

    def test_wrong_engineering_type_is_excluded_from_bare_fallback(self):
        channels = [
            ChannelForDetection("VA", VOLTAGE),
            ChannelForDetection("IA", CURRENT),
            ChannelForDetection("VB", POWER),
        ]
        detected = detect_engineering_contexts(channels)
        assert len(detected) == 1
        names = {m.channel_name for m in detected[0].members}
        assert names == {"VA", "IA"}
        assert "VB" not in names


class TestStructuredPhaseMetadata:
    def test_structured_metadata_used_when_available_and_recognized(self):
        channels = [
            ChannelForDetection("ALPHA1_VA", VOLTAGE, phase_label="R"),
            ChannelForDetection("ALPHA1_IA", CURRENT),
        ]
        detected = detect_engineering_contexts(channels)
        context = detected[0]
        member = next(m for m in context.members if m.channel_name == "ALPHA1_VA")
        assert member.phase_source == PHASE_SOURCE_STRUCTURED_METADATA
        assert member.original_phase_label == "R"
        # Convention evidence pool for this root now includes "R" (from
        # metadata) and "A" (from ALPHA1_IA's own name) -- genuinely
        # conflicting exclusive evidence -- so this specific scenario
        # ends up needs_review, which is itself the correct conservative
        # outcome (never silently pick one convention over the other).
        assert context.status == STATUS_NEEDS_REVIEW

    def test_structured_metadata_resolves_cleanly_when_internally_consistent(self):
        channels = [
            ChannelForDetection("ALPHA1_VA", VOLTAGE, phase_label="L1"),
            ChannelForDetection("ALPHA1_VB", VOLTAGE, phase_label="L2"),
            ChannelForDetection("ALPHA1_VC", VOLTAGE, phase_label="L3"),
        ]
        detected = detect_engineering_contexts(channels)
        assert len(detected) == 1
        context = detected[0]
        assert context.status == STATUS_SUGGESTED
        assert _phase_by_channel(context, "ALPHA1_VA") == PHASE_A
        assert _phase_by_channel(context, "ALPHA1_VB") == PHASE_B
        assert _phase_by_channel(context, "ALPHA1_VC") == PHASE_C
        for m in context.members:
            assert m.phase_source == PHASE_SOURCE_STRUCTURED_METADATA

    def test_unrecognized_structured_metadata_falls_back_to_name(self):
        channels = [
            ChannelForDetection("ALPHA1_VA", VOLTAGE, phase_label="not-a-phase-token"),
            ChannelForDetection("ALPHA1_IA", CURRENT),
        ]
        detected = detect_engineering_contexts(channels)
        context = detected[0]
        member = next(m for m in context.members if m.channel_name == "ALPHA1_VA")
        assert member.phase_source == PHASE_SOURCE_DETECTED_FROM_NAME
        assert member.phase == PHASE_A


class TestUnknownPhaseNeverGuessed:
    def test_lone_ambiguous_b_yields_unknown_phase_and_needs_review(self):
        channels = [ChannelForDetection("ALPHA1_VB", VOLTAGE)]
        detected = detect_engineering_contexts(channels)
        assert len(detected) == 1
        context = detected[0]
        assert context.status == STATUS_NEEDS_REVIEW
        assert context.members[0].phase == PHASE_UNKNOWN


class TestUngroupableChannelsExcluded:
    def test_channel_with_no_recognizable_suffix_excluded_entirely(self):
        channels = [ChannelForDetection("MISC_SIGNAL", VOLTAGE), ChannelForDetection("ALPHA1_VA", VOLTAGE)]
        detected = detect_engineering_contexts(channels)
        assert len(detected) == 1
        assert {m.channel_name for m in detected[0].members} == {"ALPHA1_VA"}

    def test_non_bare_channel_with_no_bay_root_excluded(self):
        """"METER_A" has a recognizable phase suffix but no trailing
        kind marker before that suffix, so it is not eligible for the
        rootless bare-role fallback."""
        channels = [ChannelForDetection("METER_A", VOLTAGE)]
        detected = detect_engineering_contexts(channels)
        assert detected == []
