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
