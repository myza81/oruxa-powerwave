"""Tests for app.domain.measurement_group_detection (Slice 2 of
DEC-050): the pure, deterministic phase-suffix clustering algorithm --
no registry, no service, no I/O. See
test_measurement_group_service.py's TestGenerateSuggestedGroupsForSource
for the persistence layer built on top of this.
"""

from __future__ import annotations

from app.domain.channel_classification import CURRENT, FREQUENCY, POWER, UNDEFINED, VOLTAGE
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_NEEDS_REVIEW, STATUS_SUGGESTED
from app.domain.measurement_group_detection import detect_measurement_groups


def _by_display_name(detected, name):
    return next(d for d in detected if d.display_name == name)


class TestCanonicalWorkedExamples:
    """The exact worked examples from PER_UNIT_MEASUREMENT_MODEL.md
    section 15."""

    def test_ibt1_hv_current_triplet(self):
        channels = [("IBT1 HV IR", CURRENT), ("IBT1 HV IY", CURRENT), ("IBT1 HV IB", CURRENT)]
        detected = detect_measurement_groups(channels)
        assert len(detected) == 1
        group = detected[0]
        assert group.kind == KIND_CURRENT
        assert group.display_name == "IBT1 HV CURRENT"
        assert set(group.channel_names) == {"IBT1 HV IR", "IBT1 HV IY", "IBT1 HV IB"}
        assert group.status == STATUS_SUGGESTED

    def test_ibt1_hv_and_lv_are_two_separate_groups(self):
        channels = [
            ("IBT1 HV IR", CURRENT), ("IBT1 HV IY", CURRENT), ("IBT1 HV IB", CURRENT),
            ("IBT1 LV IR", CURRENT), ("IBT1 LV IY", CURRENT), ("IBT1 LV IB", CURRENT),
        ]
        detected = detect_measurement_groups(channels)
        assert len(detected) == 2
        hv = _by_display_name(detected, "IBT1 HV CURRENT")
        lv = _by_display_name(detected, "IBT1 LV CURRENT")
        assert set(hv.channel_names) == {"IBT1 HV IR", "IBT1 HV IY", "IBT1 HV IB"}
        assert set(lv.channel_names) == {"IBT1 LV IR", "IBT1 LV IY", "IBT1 LV IB"}
        # Never merged into one group despite sharing "IBT1" and "I".
        assert not (set(hv.channel_names) & set(lv.channel_names))

    def test_north_bus_voltage_triplet(self):
        channels = [("NORTH BUS VR", VOLTAGE), ("NORTH BUS VY", VOLTAGE), ("NORTH BUS VB", VOLTAGE)]
        detected = detect_measurement_groups(channels)
        assert len(detected) == 1
        group = detected[0]
        assert group.kind == KIND_VOLTAGE
        assert group.display_name == "NORTH BUS VOLTAGE"
        assert group.status == STATUS_SUGGESTED


class TestPhaseTokenVariants:
    def test_abc_phase_naming(self):
        channels = [("VA", VOLTAGE), ("VB", VOLTAGE), ("VC", VOLTAGE)]
        detected = detect_measurement_groups(channels)
        assert len(detected) == 1
        assert detected[0].display_name == "VOLTAGE"
        assert set(detected[0].channel_names) == {"VA", "VB", "VC"}

    def test_explicit_neutral_suffix(self):
        channels = [("VAN", VOLTAGE), ("VBN", VOLTAGE), ("VCN", VOLTAGE)]
        detected = detect_measurement_groups(channels)
        assert len(detected) == 1
        assert set(detected[0].channel_names) == {"VAN", "VBN", "VCN"}
        assert detected[0].status == STATUS_SUGGESTED

    def test_line_to_line_pair_suffix_clusters_together(self):
        channels = [("275KV VRY", VOLTAGE), ("275KV VYB", VOLTAGE), ("275KV VBR", VOLTAGE)]
        detected = detect_measurement_groups(channels)
        assert len(detected) == 1
        group = detected[0]
        assert group.display_name == "275KV VOLTAGE"
        assert set(group.channel_names) == {"275KV VRY", "275KV VYB", "275KV VBR"}
        assert group.status == STATUS_SUGGESTED

    def test_current_channels_use_single_and_neutral_tokens_only(self):
        # Current has no line-to-line concept -- pair tokens (RY/YB/BR
        # etc.) are never checked for a Current channel, only the
        # single-letter/explicit-neutral forms.
        channels = [("IBT1 IR", CURRENT), ("IBT1 IY", CURRENT)]
        detected = detect_measurement_groups(channels)
        assert len(detected) == 1
        assert detected[0].kind == KIND_CURRENT
        assert set(detected[0].channel_names) == {"IBT1 IR", "IBT1 IY"}


class TestExclusionRules:
    def test_non_voltage_current_engineering_types_are_ignored(self):
        channels = [("F", FREQUENCY), ("P", POWER), ("X", UNDEFINED)]
        assert detect_measurement_groups(channels) == []

    def test_channel_with_no_recognizable_phase_suffix_is_excluded(self):
        channels = [("SPARE1", VOLTAGE), ("VR", VOLTAGE)]
        detected = detect_measurement_groups(channels)
        # SPARE1 never appears in any detected cluster.
        all_names = {name for group in detected for name in group.channel_names}
        assert "SPARE1" not in all_names
        assert "VR" in all_names

    def test_bare_single_letter_channel_name_is_excluded(self):
        # A channel literally named just "R" has no prefix content left
        # after stripping the phase letter -- excluded rather than
        # clustered under an empty base name.
        channels = [("R", VOLTAGE)]
        assert detect_measurement_groups(channels) == []

    def test_mixed_engineering_types_never_merge_into_one_cluster(self):
        # VA (Voltage) and IA (Current) both strip to base "" or "I"/"V"-
        # stripped forms, but kind is part of the cluster key -- never
        # merged even if base names happened to coincide.
        channels = [("VR", VOLTAGE), ("IR", CURRENT)]
        detected = detect_measurement_groups(channels)
        assert len(detected) == 2
        kinds = {g.kind for g in detected}
        assert kinds == {KIND_VOLTAGE, KIND_CURRENT}


class TestSingleChannelGroups:
    def test_a_single_recognized_phase_channel_with_no_siblings_is_still_suggested(self):
        channels = [("FEEDER1 VR", VOLTAGE)]
        detected = detect_measurement_groups(channels)
        assert len(detected) == 1
        assert detected[0].channel_names == ["FEEDER1 VR"]
        assert detected[0].status == STATUS_SUGGESTED


class TestNeedsReview:
    def test_duplicate_phase_token_within_one_cluster_needs_review(self):
        # Two distinct channel names both resolving to phase R within
        # the same base/kind cluster is a genuine internal conflict --
        # never silently pick one.
        channels = [("BUS1 VR", VOLTAGE), ("BUS1 VR", VOLTAGE)]
        detected = detect_measurement_groups(channels)
        assert len(detected) == 1
        assert detected[0].status == STATUS_NEEDS_REVIEW

    def test_mixed_pair_and_single_representation_needs_review(self):
        # "BUS1 VR" (phase-to-reference) and "BUS1 VRY" (phase-to-phase)
        # share base name "BUS1 V" but carry contradictory
        # representations -- flagged, never resolved one way.
        channels = [("BUS1 VR", VOLTAGE), ("BUS1 VRY", VOLTAGE)]
        detected = detect_measurement_groups(channels)
        assert len(detected) == 1
        assert detected[0].status == STATUS_NEEDS_REVIEW

    def test_mixed_single_and_neutral_representation_is_not_a_conflict(self):
        # Single-letter and explicit-neutral suffixes are both
        # phase-to-reference evidence -- they agree, not conflict.
        channels = [("BUS1 VR", VOLTAGE), ("BUS1 VYN", VOLTAGE)]
        detected = detect_measurement_groups(channels)
        assert len(detected) == 1
        assert detected[0].status == STATUS_SUGGESTED

    def test_needs_review_group_is_never_confirmed_by_detection(self):
        channels = [("BUS1 VR", VOLTAGE), ("BUS1 VR", VOLTAGE)]
        detected = detect_measurement_groups(channels)
        assert detected[0].status != "confirmed"


class TestDeterminism:
    def test_same_input_produces_the_same_output_every_time(self):
        channels = [("NORTH BUS VR", VOLTAGE), ("NORTH BUS VY", VOLTAGE), ("NORTH BUS VB", VOLTAGE)]
        first = detect_measurement_groups(channels)
        second = detect_measurement_groups(channels)
        assert [(g.kind, g.display_name, g.channel_names, g.status) for g in first] == [
            (g.kind, g.display_name, g.channel_names, g.status) for g in second
        ]

    def test_empty_input_produces_empty_output(self):
        assert detect_measurement_groups([]) == []

    def test_evidence_matches_channel_names(self):
        channels = [("VR", VOLTAGE), ("VY", VOLTAGE)]
        detected = detect_measurement_groups(channels)
        assert set(detected[0].evidence) == set(detected[0].channel_names)
