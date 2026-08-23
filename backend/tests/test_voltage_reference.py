"""Unit tests for app.domain.voltage_reference's automatic Voltage
Reference detection (Phase 5C-UAT, DEC-049 addendum) -- the owner's own
exact naming examples from the UAT feedback spec, section 16.
"""

from __future__ import annotations

from app.domain.voltage_reference import (
    LINE_TO_GROUND,
    LINE_TO_LINE,
    REASON_CONFLICTING,
    REASON_DETECTED,
    REASON_NO_CHANNELS,
    REASON_NO_PATTERN,
    detect_voltage_reference,
)


class TestLineToGroundDetection:
    def test_vr_vy_vb(self):
        result = detect_voltage_reference(["VR", "VY", "VB"])
        assert result.reference == LINE_TO_GROUND
        assert result.reason == REASON_DETECTED
        assert set(result.evidence_names) == {"VR", "VY", "VB"}

    def test_va_vb_vc(self):
        result = detect_voltage_reference(["VA", "VB", "VC"])
        assert result.reference == LINE_TO_GROUND

    def test_van_vbn_vcn(self):
        result = detect_voltage_reference(["VAN", "VBN", "VCN"])
        assert result.reference == LINE_TO_GROUND

    def test_vrn_vyn_vbn(self):
        result = detect_voltage_reference(["VRN", "VYN", "VBN"])
        assert result.reference == LINE_TO_GROUND


class TestLineToLineDetection:
    def test_vry_vyb_vbr(self):
        result = detect_voltage_reference(["VRY", "VYB", "VBR"])
        assert result.reference == LINE_TO_LINE
        assert result.reason == REASON_DETECTED
        assert set(result.evidence_names) == {"VRY", "VYB", "VBR"}

    def test_vab_vbc_vca(self):
        result = detect_voltage_reference(["VAB", "VBC", "VCA"])
        assert result.reference == LINE_TO_LINE

    def test_vll(self):
        result = detect_voltage_reference(["VLL"])
        assert result.reference == LINE_TO_LINE

    def test_vbus(self):
        result = detect_voltage_reference(["VBUS"])
        assert result.reference == LINE_TO_LINE

    def test_bus_voltage_with_space(self):
        result = detect_voltage_reference(["BUS VOLTAGE"])
        assert result.reference == LINE_TO_LINE

    def test_pair_name_is_never_misread_as_a_bare_single_letter(self):
        # The owner's own explicit warning: "R/Y/B present... must NOT
        # automatically mean Line-to-Ground when the names clearly
        # indicate combinations such as VRY/VYB/VBR."
        result = detect_voltage_reference(["VRY"])
        assert result.reference == LINE_TO_LINE


class TestAmbiguousAndConflictingEvidence:
    def test_no_recognizable_pattern_never_claims_confidence(self):
        result = detect_voltage_reference(["CH1", "CH2", "CH3"])
        assert result.reference is None
        assert result.reason == REASON_NO_PATTERN

    def test_conflicting_evidence_never_silently_resolved(self):
        result = detect_voltage_reference(["VRY", "VA"])
        assert result.reference is None
        assert result.reason == REASON_CONFLICTING

    def test_no_channels_at_all(self):
        result = detect_voltage_reference([])
        assert result.reference is None
        assert result.reason == REASON_NO_CHANNELS

    def test_mixed_recognized_and_unrecognized_names_still_detects_from_the_recognized_ones(self):
        result = detect_voltage_reference(["VR", "VY", "VB", "AUX1"])
        assert result.reference == LINE_TO_GROUND
        assert set(result.evidence_names) == {"VR", "VY", "VB"}


class TestExplicitPhaseEvidenceOutranksGenericVocabulary:
    """DEC-050 Slice 3 correction: explicit phase-suffix evidence must
    win over generic location/equipment vocabulary such as "BUS", even
    when that vocabulary appears earlier in a longer channel name. See
    PER_UNIT_MEASUREMENT_MODEL.md's own corrected principle and this
    module's own docstring for the full before/after explanation."""

    def test_north_bus_va_vb_vc_is_line_to_ground_not_line_to_line(self):
        result = detect_voltage_reference(["NORTH BUS VA", "NORTH BUS VB", "NORTH BUS VC"])
        assert result.reference == LINE_TO_GROUND
        assert result.reason == REASON_DETECTED
        assert set(result.evidence_names) == {"NORTH BUS VA", "NORTH BUS VB", "NORTH BUS VC"}

    def test_north_bus_vr_vy_vb_is_line_to_ground(self):
        result = detect_voltage_reference(["NORTH BUS VR", "NORTH BUS VY", "NORTH BUS VB"])
        assert result.reference == LINE_TO_GROUND

    def test_275kv_bus_vr_vy_vb_is_line_to_ground(self):
        result = detect_voltage_reference(["275KV BUS VR", "275KV BUS VY", "275KV BUS VB"])
        assert result.reference == LINE_TO_GROUND

    def test_275kv_bus_van_vbn_vcn_is_line_to_ground(self):
        result = detect_voltage_reference(["275KV BUS VAN", "275KV BUS VBN", "275KV BUS VCN"])
        assert result.reference == LINE_TO_GROUND

    def test_explicit_pair_still_wins_even_with_bus_present(self):
        # An explicit LL pair and the generic "BUS" text agree here, but
        # this proves the pair evidence itself is what is being matched,
        # not merely the "BUS" fallback happening to also say LL.
        result = detect_voltage_reference(["275KV BUS VRY", "275KV BUS VYB", "275KV BUS VBR"])
        assert result.reference == LINE_TO_LINE

    def test_generic_vbus_with_no_phase_letter_remains_line_to_line(self):
        # No explicit phase suffix at all here -- the generic fallback
        # must still apply exactly as before this correction.
        result = detect_voltage_reference(["VBUS"])
        assert result.reference == LINE_TO_LINE

    def test_generic_bus_voltage_with_no_phase_letter_remains_line_to_line(self):
        result = detect_voltage_reference(["BUS VOLTAGE"])
        assert result.reference == LINE_TO_LINE

    def test_word_fused_v_is_not_misread_as_phase_evidence(self):
        # "AVR" (Automatic Voltage Regulator, a real power-system
        # abbreviation) has a "V" immediately followed by "R", but that
        # "V" is fused into an unrelated word, not a genuine, separated
        # phase-channel marker -- must remain unrecognized, exactly as
        # it did before this correction (never a new false positive).
        result = detect_voltage_reference(["AVR"])
        assert result.reference is None
        assert result.reason == REASON_NO_PATTERN

    def test_word_fused_v_does_not_disturb_a_confident_result_from_real_evidence(self):
        result = detect_voltage_reference(["NORTH BUS VA", "NORTH BUS VB", "NORTH BUS VC", "AVR"])
        assert result.reference == LINE_TO_GROUND
        assert "AVR" not in result.evidence_names

    def test_hyphen_and_underscore_separators_are_recognized_word_boundaries(self):
        result = detect_voltage_reference(["NORTH-BUS-VA", "NORTH-BUS-VB", "NORTH-BUS-VC"])
        assert result.reference == LINE_TO_GROUND

    def test_explicit_lg_evidence_conflicting_with_generic_bus_only_evidence_is_still_conflicting(self):
        # A channel with ONLY generic "BUS" evidence (no phase letter at
        # all) mixed with a channel carrying explicit LG evidence must
        # still be reported as genuinely conflicting -- never silently
        # resolved by letting the explicit evidence steamroll a
        # DIFFERENT channel's own distinct (if weaker) LL evidence.
        result = detect_voltage_reference(["NORTH BUS VA", "SOME BUS COUPLER"])
        assert result.reference is None
        assert result.reason == REASON_CONFLICTING
