"""Tests for app.domain.auto_base_evidence (DEC-050 Slice 5A).

Covers all required scenarios from the Slice 5A spec:

  Voltage:
    - Primary L-L recording
    - Primary L-G recording
    - Secondary L-L recording
    - Secondary L-G recording
    - BEN with unknown measurement side
    - BEN with primary_rating providing low-confidence candidate
    - Nominal voltage name token versus VT winding rating (C2)
    - Name token does not establish measurement side (C4)
    - Multiple bays / different voltage levels (independent calls)
    - Conflicting nominal information
    - Missing or invalid ratios
    - Mixed Primary/Secondary channels (contradiction)
    - Incomplete phase set (single-channel group)
    - Incorrect / ambiguous units
    - Candidate determinable but NOT sufficient for automatic authority

  Current:
    - CT primary rating explicitly excluded (DEC-050 §11 / C5)
    - Nominal equipment current versus CT primary rating
    - No auto-Ibase from channel descriptors alone
    - Mixed measurement sides

No test assumes that an unknown reference side is known merely because
the nominal voltage is recognizable from a channel name.
"""

from __future__ import annotations

import math
import pytest

from app.domain.auto_base_evidence import (
    REASON_CONTRADICTORY_NOMINAL,
    REASON_CT_PRIMARY_EXCLUDED,
    REASON_MIXED_SIDES,
    REASON_NO_EQUIPMENT_CURRENT,
    REASON_NO_NOMINAL_EVIDENCE,
    REASON_REFERENCE_CONFLICTED,
    REASON_REFERENCE_UNDETERMINED,
    REASON_SECONDARY_REQUIRES_REDESIGN,
    REASON_SIDE_UNKNOWN,
    REASON_UNIT_UNRECOGNIZED,
    REASON_NO_VOLTAGE_CHANNELS,
    REASON_NO_CURRENT_CHANNELS,
    SQRT_3,
    ChannelAutoMetadata,
    resolve_current_group_evidence,
    resolve_voltage_group_evidence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vchan(
    name: str,
    unit: str = "kV",
    side: str = "unknown",
    primary_ratio: float | None = None,
    secondary_ratio: float | None = None,
) -> ChannelAutoMetadata:
    return ChannelAutoMetadata(
        name=name,
        engineering_type="voltage",
        unit=unit,
        measurement_side=side,
        primary_ratio=primary_ratio,
        secondary_ratio=secondary_ratio,
    )


def _ichan(
    name: str,
    unit: str = "kA",
    side: str = "unknown",
    primary_ratio: float | None = None,
    secondary_ratio: float | None = None,
) -> ChannelAutoMetadata:
    return ChannelAutoMetadata(
        name=name,
        engineering_type="current",
        unit=unit,
        measurement_side=side,
        primary_ratio=primary_ratio,
        secondary_ratio=secondary_ratio,
    )


# ---------------------------------------------------------------------------
# Voltage — Primary side
# ---------------------------------------------------------------------------

class TestPrimaryLLVoltage:
    """Primary-side recording using a line-to-line VT (PS='P', L-L channel names)."""

    def test_primary_ll_produces_nominal_candidate(self):
        """MCRS 275 kV bus, L-L VT, three phases."""
        channels = [
            _vchan("MCRS VRY", unit="kV", side="primary", primary_ratio=275.0),
            _vchan("MCRS VYB", unit="kV", side="primary", primary_ratio=275.0),
            _vchan("MCRS VBR", unit="kV", side="primary", primary_ratio=275.0),
        ]
        ev = resolve_voltage_group_evidence(channels)

        assert ev.channel_reference == "line_to_line"
        assert ev.measurement_side == "primary"
        assert ev.side_declared is True
        assert len(ev.primary_nominal_candidates) >= 1
        # At least one candidate with medium or high confidence
        assert any(c.confidence in ("high", "medium") for c in ev.primary_nominal_candidates)
        # All candidates resolve to 275 kV
        for c in ev.primary_nominal_candidates:
            assert math.isclose(c.value_kv, 275.0, rel_tol=0.05)
        assert ev.primary_nominal_consistent is True
        assert ev.has_contradictions is False
        assert ev.sufficient_for_auto_nominal is True
        assert ev.sufficient_for_auto_side is True

    def test_primary_ll_winding_candidate_source(self):
        """Winding-field candidate carries expected source tag."""
        channels = [_vchan("MCRS VRY", unit="kV", side="primary", primary_ratio=275.0)]
        ev = resolve_voltage_group_evidence(channels)
        winding_cands = [c for c in ev.primary_nominal_candidates if c.source == "comtrade_primary_ll"]
        assert winding_cands, "Expected comtrade_primary_ll source candidate"
        assert math.isclose(winding_cands[0].value_kv, 275.0, rel_tol=1e-6)

    def test_primary_ll_v_unit(self):
        """Winding ratio in V (not kV) is normalized correctly."""
        channels = [_vchan("MCRS VRY", unit="V", side="primary", primary_ratio=275_000.0)]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.channel_reference == "line_to_line"
        winding_cands = [c for c in ev.primary_nominal_candidates if c.source == "comtrade_primary_ll"]
        assert winding_cands
        assert math.isclose(winding_cands[0].value_kv, 275.0, rel_tol=1e-4)
        assert ev.sufficient_for_auto_nominal is True

    def test_primary_ll_no_ratio_name_token(self):
        """Name token only: 275KV in channel name, no winding ratio."""
        channels = [_vchan("275KV VRY", unit="kV", side="primary")]
        ev = resolve_voltage_group_evidence(channels)
        name_cands = [c for c in ev.primary_nominal_candidates if c.source == "name_token"]
        assert name_cands
        assert math.isclose(name_cands[0].value_kv, 275.0, rel_tol=1e-6)
        assert name_cands[0].confidence == "medium"


class TestPrimaryLGVoltage:
    """Primary-side recording using a line-to-ground (phase-winding) VT."""

    def test_primary_lg_132kv_bus(self):
        """KPDN1 132 kV bus, L-G VT: primary winding 76.2 kV (phase-to-ground).
        Nominal L-L = 76.2 × √3 = 131.982 kV ≈ 132 kV.
        """
        channels = [
            _vchan("KPDN1 VRN", unit="kV", side="primary", primary_ratio=76.2),
            _vchan("KPDN1 VYN", unit="kV", side="primary", primary_ratio=76.2),
            _vchan("KPDN1 VBN", unit="kV", side="primary", primary_ratio=76.2),
        ]
        ev = resolve_voltage_group_evidence(channels)

        assert ev.channel_reference == "line_to_ground"
        assert ev.measurement_side == "primary"
        assert ev.side_declared is True
        winding_cands = [c for c in ev.primary_nominal_candidates if "lg" in c.source]
        assert winding_cands
        expected_nominal_ll = 76.2 * SQRT_3
        assert math.isclose(winding_cands[0].value_kv, expected_nominal_ll, rel_tol=1e-4)
        assert ev.has_contradictions is False
        assert ev.sufficient_for_auto_nominal is True

    def test_primary_lg_v_unit(self):
        """L-G VT with primary winding in V: 76200 V → 76.2 kV → 132 kV L-L."""
        channels = [_vchan("KPDN1 VRN", unit="V", side="primary", primary_ratio=76_200.0)]
        ev = resolve_voltage_group_evidence(channels)
        winding_cands = [c for c in ev.primary_nominal_candidates if "lg" in c.source]
        assert winding_cands
        expected = 76.2 * SQRT_3
        assert math.isclose(winding_cands[0].value_kv, expected, rel_tol=1e-4)

    def test_primary_lg_winding_distinct_from_name_token(self):
        """Channel name carries kV token AND winding field — both yield candidates.
        Name token: '132KV VRN' → 132.0 kV.
        Winding field: 76.2 kV × √3 = 131.982 kV ≈ 132 kV.
        Both should be present and consistent.
        """
        channels = [
            _vchan("132KV VRN", unit="kV", side="primary", primary_ratio=76.2),
        ]
        ev = resolve_voltage_group_evidence(channels)
        assert len(ev.primary_nominal_candidates) >= 2  # name token + winding
        all_kvs = [c.value_kv for c in ev.primary_nominal_candidates]
        assert _all_close(all_kvs, 132.0, rel_tol=0.01)
        assert ev.primary_nominal_consistent is True
        assert ev.has_contradictions is False

    def test_primary_lg_winding_is_not_nominal_voltage_directly(self):
        """Correction C2: the primary winding (76.2 kV) is NOT the nominal voltage.
        The nominal primary L-L is 76.2 × √3 = 132 kV.
        The candidate value must NOT be 76.2 kV.
        """
        channels = [_vchan("KPDN1 VRN", unit="kV", side="primary", primary_ratio=76.2)]
        ev = resolve_voltage_group_evidence(channels)
        for c in ev.primary_nominal_candidates:
            if "lg" in c.source:
                assert not math.isclose(c.value_kv, 76.2, rel_tol=1e-3), (
                    "Winding rating (76.2 kV L-G) must not appear raw as nominal L-L"
                )
                assert math.isclose(c.value_kv, 76.2 * SQRT_3, rel_tol=1e-4)


# ---------------------------------------------------------------------------
# Voltage — Secondary side
# ---------------------------------------------------------------------------

class TestSecondaryLLVoltage:
    """Secondary-side recording, line-to-line VT (PS='S')."""

    def test_secondary_ll_measured_voltage_captured(self):
        """132 kV bus, 110 V L-L secondary VT, PS='S'.
        secondary_ratio = 0.110 kV.  Measured secondary = 110 V L-L.
        """
        channels = [
            _vchan("JMHE VRY", unit="kV", side="secondary", primary_ratio=132.0, secondary_ratio=0.110),
            _vchan("JMHE VYB", unit="kV", side="secondary", primary_ratio=132.0, secondary_ratio=0.110),
        ]
        ev = resolve_voltage_group_evidence(channels)

        assert ev.measurement_side == "secondary"
        assert ev.side_declared is True
        assert ev.channel_reference == "line_to_line"
        assert ev.secondary_measured is not None
        assert math.isclose(ev.secondary_measured.value_kv, 0.110, rel_tol=1e-4)
        assert ev.secondary_measured.channel_reference == "line_to_line"

    def test_secondary_ll_primary_ratio_gives_low_confidence_nominal(self):
        """Primary winding (132 kV) on PS='S' channel → low-confidence primary nominal."""
        channels = [
            _vchan("JMHE VRY", unit="kV", side="secondary", primary_ratio=132.0, secondary_ratio=0.110),
        ]
        ev = resolve_voltage_group_evidence(channels)
        low_cands = [c for c in ev.primary_nominal_candidates if c.confidence == "low" and "primary" in c.source]
        assert low_cands, "Expected low-confidence primary nominal from winding ratio"
        assert math.isclose(low_cands[0].value_kv, 132.0, rel_tol=1e-4)

    def test_secondary_ll_not_sufficient_for_auto_nominal(self):
        """C1: secondary-side evidence is not sufficient for automatic nominal_voltage_ll_kv
        because that field represents the primary system quantity and requires a redesign.
        """
        channels = [
            _vchan("JMHE VRY", unit="kV", side="secondary", primary_ratio=132.0, secondary_ratio=0.110),
        ]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.sufficient_for_auto_nominal is False
        assert REASON_SECONDARY_REQUIRES_REDESIGN in ev.insufficient_reasons

    def test_secondary_ll_measured_voltage_is_not_primary_nominal(self):
        """C1: secondary_measured.value_kv (0.110 kV) must NOT be used as
        nominal_voltage_ll_kv (132 kV) without redesign.  The two quantities
        are captured separately.
        """
        channels = [
            _vchan("JMHE VRY", unit="kV", side="secondary", primary_ratio=132.0, secondary_ratio=0.110),
        ]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.secondary_measured is not None
        # Secondary measured is 110 V, NOT 132 kV
        assert math.isclose(ev.secondary_measured.value_kv, 0.110, rel_tol=1e-4)
        assert not math.isclose(ev.secondary_measured.value_kv, 132.0, rel_tol=0.5)

    def test_secondary_ll_primary_ll_from_ratio_in_secondary_measured(self):
        """MeasuredSecondaryVoltage.primary_ll_kv_from_ratio should be 132 kV."""
        channels = [
            _vchan("JMHE VRY", unit="kV", side="secondary", primary_ratio=132.0, secondary_ratio=0.110),
        ]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.secondary_measured is not None
        assert ev.secondary_measured.primary_ll_kv_from_ratio is not None
        assert math.isclose(ev.secondary_measured.primary_ll_kv_from_ratio, 132.0, rel_tol=1e-4)


class TestSecondaryLGVoltage:
    """Secondary-side recording, phase-winding (L-G) VT (PS='S')."""

    def test_secondary_lg_132kv_bus(self):
        """132 kV bus, 63.5 V phase-winding secondary VT, PS='S'.
        secondary_ratio = 0.0635 kV.  Measured = 63.5 V L-G.
        """
        channels = [
            _vchan("KPDN1 VA", unit="kV", side="secondary", primary_ratio=76.2, secondary_ratio=0.0635),
            _vchan("KPDN1 VB", unit="kV", side="secondary", primary_ratio=76.2, secondary_ratio=0.0635),
        ]
        ev = resolve_voltage_group_evidence(channels)

        assert ev.measurement_side == "secondary"
        assert ev.channel_reference == "line_to_ground"
        assert ev.secondary_measured is not None
        assert math.isclose(ev.secondary_measured.value_kv, 0.0635, rel_tol=1e-3)
        assert ev.secondary_measured.channel_reference == "line_to_ground"

    def test_secondary_lg_va_channel_is_lg_not_ll(self):
        """Correction C3: 'VA' channel reference is line-to-ground (single phase token),
        NOT line-to-line, even though the VT might have a 110 V L-L secondary rating.
        The reference comes from the channel name, not the winding topology.
        """
        channels = [
            _vchan("VA", unit="kV", side="secondary", primary_ratio=76.2, secondary_ratio=0.110),
        ]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.channel_reference == "line_to_ground", (
            "'VA' must resolve to line_to_ground via channel name (C3)"
        )

    def test_secondary_lg_primary_ll_via_sqrt3(self):
        """For secondary L-G with primary winding 76.2 kV:
        primary_ll_kv_from_ratio = 76.2 × √3 = 131.982 kV ≈ 132 kV.
        """
        channels = [
            _vchan("KPDN1 VA", unit="kV", side="secondary", primary_ratio=76.2, secondary_ratio=0.0635),
        ]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.secondary_measured is not None
        assert ev.secondary_measured.primary_ll_kv_from_ratio is not None
        assert math.isclose(
            ev.secondary_measured.primary_ll_kv_from_ratio, 76.2 * SQRT_3, rel_tol=1e-4
        )


# ---------------------------------------------------------------------------
# BEN recordings (measurement_side always "unknown")
# ---------------------------------------------------------------------------

class TestBENMeasurement:
    """BEN files: measurement_side always 'unknown'; no PS flag."""

    def test_ben_name_token_gives_nominal_candidate(self):
        """Channel name '275KV VRY' → 275 kV nominal candidate (medium confidence).
        Side remains unknown — name token does not establish side (C4).
        """
        channels = [_vchan("275KV VRY", unit="kV", side="unknown", primary_ratio=275.0)]
        ev = resolve_voltage_group_evidence(channels)

        assert ev.measurement_side == "unknown"
        assert ev.side_declared is False
        # Name token candidate present
        name_cands = [c for c in ev.primary_nominal_candidates if c.source == "name_token"]
        assert name_cands
        assert math.isclose(name_cands[0].value_kv, 275.0, rel_tol=1e-6)
        assert name_cands[0].confidence == "medium"

    def test_ben_name_token_does_not_establish_side(self):
        """C4: despite the nominal voltage being known, side stays 'unknown'."""
        channels = [_vchan("275KV VRY", unit="kV", side="unknown")]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.measurement_side == "unknown"
        assert ev.sufficient_for_auto_side is False
        assert REASON_SIDE_UNKNOWN in ev.insufficient_reasons

    def test_ben_primary_rating_no_name_token(self):
        """BEN channel 'VA' with primary_rating=76.2 kV: low-confidence winding candidate.
        No name token; channel_reference = line_to_ground.
        """
        channels = [_vchan("VA", unit="kV", side="unknown", primary_ratio=76.2)]
        ev = resolve_voltage_group_evidence(channels)

        assert ev.channel_reference == "line_to_ground"
        # Winding candidate present but low confidence (side unknown)
        winding_cands = [c for c in ev.primary_nominal_candidates if "primary" in c.source]
        assert winding_cands
        assert winding_cands[0].confidence == "low"
        # Winding value is 76.2 × √3 (L-G geometry)
        assert math.isclose(winding_cands[0].value_kv, 76.2 * SQRT_3, rel_tol=1e-4)

    def test_ben_low_confidence_candidate_not_sufficient_for_auto(self):
        """Low-confidence-only evidence is not sufficient for automatic authority."""
        channels = [_vchan("VA", unit="kV", side="unknown", primary_ratio=76.2)]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.sufficient_for_auto_nominal is False
        # But a candidate IS present
        assert len(ev.primary_nominal_candidates) >= 1

    def test_ben_no_name_token_no_ratio(self):
        """BEN channel 'POWER' (no token, no ratio): no nominal evidence."""
        channels = [_vchan("POWER", unit="kV", side="unknown")]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.primary_nominal_candidates == ()
        assert ev.sufficient_for_auto_nominal is False
        assert REASON_NO_NOMINAL_EVIDENCE in ev.insufficient_reasons


# ---------------------------------------------------------------------------
# Nominal voltage versus VT winding rating (C2)
# ---------------------------------------------------------------------------

class TestNominalVsWinding:
    """Correction C2: winding ratings are transformation data, not nominal values."""

    def test_primary_winding_is_candidate_not_authoritative(self):
        """primary_ratio is flagged as 'transformation data' in derivation text."""
        channels = [_vchan("MCRS VRY", unit="kV", side="primary", primary_ratio=275.0)]
        ev = resolve_voltage_group_evidence(channels)
        winding_cands = [c for c in ev.primary_nominal_candidates if "primary" in c.source]
        assert winding_cands
        assert "C2" in winding_cands[0].derivation or "transformation" in winding_cands[0].derivation.lower()

    def test_lg_winding_requires_sqrt3_correction(self):
        """L-G primary winding 76.2 kV ≠ nominal L-L voltage 76.2 kV.
        The candidate must carry the √3-corrected value (≈ 132 kV), not 76.2 kV.
        """
        channels = [_vchan("KPDN1 VRN", unit="kV", side="primary", primary_ratio=76.2)]
        ev = resolve_voltage_group_evidence(channels)
        winding_cands = [c for c in ev.primary_nominal_candidates if "lg" in c.source]
        assert winding_cands
        # Must NOT be the raw winding value
        assert not math.isclose(winding_cands[0].value_kv, 76.2, rel_tol=1e-3)
        # Must be the geometry-corrected value
        assert math.isclose(winding_cands[0].value_kv, 76.2 * SQRT_3, rel_tol=1e-4)

    def test_name_token_and_winding_are_separate_candidates(self):
        """Name token and winding field are independent candidates — both listed."""
        channels = [_vchan("275KV VRY", unit="kV", side="primary", primary_ratio=275.0)]
        ev = resolve_voltage_group_evidence(channels)
        sources = {c.source for c in ev.primary_nominal_candidates}
        assert "name_token" in sources
        assert "comtrade_primary_ll" in sources

    def test_name_token_without_ratio_still_produces_candidate(self):
        """Channel with no primary_ratio but kV token: name-token candidate only."""
        channels = [_vchan("275KV VRY", unit="kV", side="primary")]
        ev = resolve_voltage_group_evidence(channels)
        assert any(c.source == "name_token" for c in ev.primary_nominal_candidates)
        assert not any("comtrade_primary" in c.source for c in ev.primary_nominal_candidates)


# ---------------------------------------------------------------------------
# Multiple bays / different voltage levels
# ---------------------------------------------------------------------------

class TestMultipleBays:
    """Groups at different voltage levels are resolved independently."""

    def test_275kv_group_independent_of_132kv_group(self):
        """Two groups at different voltage levels: each resolves its own nominal."""
        group_275 = [
            _vchan("MCRS VRY", unit="kV", side="primary", primary_ratio=275.0),
            _vchan("MCRS VYB", unit="kV", side="primary", primary_ratio=275.0),
        ]
        group_132 = [
            _vchan("KPDN1 VRN", unit="kV", side="primary", primary_ratio=76.2),
            _vchan("KPDN1 VYN", unit="kV", side="primary", primary_ratio=76.2),
        ]
        ev275 = resolve_voltage_group_evidence(group_275)
        ev132 = resolve_voltage_group_evidence(group_132)

        assert ev275.sufficient_for_auto_nominal is True
        assert ev132.sufficient_for_auto_nominal is True
        # Independent results
        kv275 = ev275.primary_nominal_candidates[0].value_kv
        kv132 = next(c.value_kv for c in ev132.primary_nominal_candidates if "lg" in c.source)
        assert math.isclose(kv275, 275.0, rel_tol=0.01)
        assert math.isclose(kv132, 76.2 * SQRT_3, rel_tol=0.01)
        # They do not affect each other
        assert ev275.has_contradictions is False
        assert ev132.has_contradictions is False

    def test_same_nominal_voltage_two_bays(self):
        """Two bays at the same nominal voltage: each resolves consistently."""
        bay_1 = [_vchan("BAY1 VRY", unit="kV", side="primary", primary_ratio=275.0)]
        bay_2 = [_vchan("BAY2 VRY", unit="kV", side="primary", primary_ratio=275.0)]
        ev1 = resolve_voltage_group_evidence(bay_1)
        ev2 = resolve_voltage_group_evidence(bay_2)
        assert ev1.sufficient_for_auto_nominal is True
        assert ev2.sufficient_for_auto_nominal is True


# ---------------------------------------------------------------------------
# Conflicting nominal information
# ---------------------------------------------------------------------------

class TestConflictingNominal:
    """Channels within one group provide contradictory nominal voltage evidence."""

    def test_contradictory_name_tokens_in_same_group(self):
        """Channels '275KV VRY' and '132KV VYB' in the same group → contradiction."""
        channels = [
            _vchan("275KV VRY", unit="kV", side="primary"),
            _vchan("132KV VYB", unit="kV", side="primary"),
        ]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.has_contradictions is True
        assert REASON_CONTRADICTORY_NOMINAL in ev.contradiction_reasons
        assert ev.sufficient_for_auto_nominal is False

    def test_contradictory_winding_ratios_in_same_group(self):
        """Channels disagree on primary winding: 275 kV vs 132 kV."""
        channels = [
            _vchan("VRY", unit="kV", side="primary", primary_ratio=275.0),
            _vchan("VYB", unit="kV", side="primary", primary_ratio=132.0),
        ]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.has_contradictions is True
        assert REASON_CONTRADICTORY_NOMINAL in ev.contradiction_reasons
        assert ev.sufficient_for_auto_nominal is False

    def test_mixed_primary_secondary_sides_is_contradiction(self):
        """Some channels PS='P', some PS='S': mixed measurement sides."""
        channels = [
            _vchan("VRY", unit="kV", side="primary", primary_ratio=275.0),
            _vchan("VYB", unit="kV", side="secondary", secondary_ratio=0.110),
        ]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.measurement_side == "unknown"
        assert ev.has_contradictions is True
        assert REASON_MIXED_SIDES in ev.contradiction_reasons

    def test_conflicting_voltage_reference_names(self):
        """L-L and L-G names in the same group: reference conflicted."""
        channels = [
            _vchan("VRY", unit="kV", side="primary", primary_ratio=275.0),  # L-L name
            _vchan("VA",  unit="kV", side="primary", primary_ratio=158.8),  # L-G name
        ]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.channel_reference is None
        assert ev.has_contradictions is True
        assert REASON_REFERENCE_CONFLICTED in ev.contradiction_reasons


# ---------------------------------------------------------------------------
# Missing / invalid ratios
# ---------------------------------------------------------------------------

class TestMissingOrInvalidRatios:
    """Channels with absent, zero, negative or non-finite ratio fields."""

    def test_none_ratio_no_winding_candidate(self):
        """primary_ratio=None → no winding candidate; name token still works."""
        channels = [_vchan("275KV VRY", unit="kV", side="primary", primary_ratio=None)]
        ev = resolve_voltage_group_evidence(channels)
        winding_cands = [c for c in ev.primary_nominal_candidates if "comtrade" in c.source]
        assert not winding_cands, "No winding candidate expected when ratio is None"
        name_cands = [c for c in ev.primary_nominal_candidates if c.source == "name_token"]
        assert name_cands, "Name token candidate should still be present"

    def test_zero_ratio_rejected(self):
        """primary_ratio=0.0 → rejected (non-positive)."""
        channels = [_vchan("VRY", unit="kV", side="primary", primary_ratio=0.0)]
        ev = resolve_voltage_group_evidence(channels)
        winding_cands = [c for c in ev.primary_nominal_candidates if "comtrade" in c.source]
        assert not winding_cands

    def test_negative_ratio_rejected(self):
        """primary_ratio=-275.0 → rejected (non-positive)."""
        channels = [_vchan("VRY", unit="kV", side="primary", primary_ratio=-275.0)]
        ev = resolve_voltage_group_evidence(channels)
        winding_cands = [c for c in ev.primary_nominal_candidates if "comtrade" in c.source]
        assert not winding_cands

    def test_nan_ratio_rejected(self):
        """primary_ratio=NaN → rejected."""
        channels = [_vchan("VRY", unit="kV", side="primary", primary_ratio=float("nan"))]
        ev = resolve_voltage_group_evidence(channels)
        winding_cands = [c for c in ev.primary_nominal_candidates if "comtrade" in c.source]
        assert not winding_cands

    def test_no_ratio_no_name_token_no_nominal_evidence(self):
        """No ratio, no name token → no nominal evidence at all."""
        channels = [_vchan("VRY", unit="kV", side="primary")]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.primary_nominal_candidates == ()
        assert ev.sufficient_for_auto_nominal is False
        assert REASON_NO_NOMINAL_EVIDENCE in ev.insufficient_reasons

    def test_partial_ratio_coverage(self):
        """Two channels: one has ratio, one does not.  Single candidate from the first."""
        channels = [
            _vchan("VRY", unit="kV", side="primary", primary_ratio=275.0),
            _vchan("VYB", unit="kV", side="primary", primary_ratio=None),
        ]
        ev = resolve_voltage_group_evidence(channels)
        # Still gets a candidate from the channel that has a ratio
        winding_cands = [c for c in ev.primary_nominal_candidates if "comtrade" in c.source]
        assert winding_cands


# ---------------------------------------------------------------------------
# Incorrect or ambiguous units
# ---------------------------------------------------------------------------

class TestIncorrectUnits:
    """Channels with unrecognized or wrong units."""

    def test_current_unit_on_voltage_channel_no_candidate(self):
        """Channel classified as voltage but unit='A': _to_kv returns None."""
        channels = [_vchan("VRY", unit="A", side="primary", primary_ratio=275.0)]
        ev = resolve_voltage_group_evidence(channels)
        winding_cands = [c for c in ev.primary_nominal_candidates if "comtrade" in c.source]
        assert not winding_cands
        assert REASON_UNIT_UNRECOGNIZED in ev.insufficient_reasons or not ev.sufficient_for_auto_nominal

    def test_none_unit_no_candidate(self):
        """unit=None → unrecognized → no winding candidate from ratio."""
        channels = [_vchan("VRY", unit=None, side="primary", primary_ratio=275.0)]
        ev = resolve_voltage_group_evidence(channels)
        winding_cands = [c for c in ev.primary_nominal_candidates if "comtrade" in c.source]
        assert not winding_cands

    def test_uppercase_kv_unit_accepted(self):
        """Unit='KV' (uppercase) → normalized to 'kv' → accepted."""
        channels = [_vchan("VRY", unit="KV", side="primary", primary_ratio=275.0)]
        ev = resolve_voltage_group_evidence(channels)
        winding_cands = [c for c in ev.primary_nominal_candidates if "comtrade" in c.source]
        assert winding_cands
        assert math.isclose(winding_cands[0].value_kv, 275.0, rel_tol=1e-6)

    def test_mw_unit_unrecognized(self):
        """unit='MW' → completely unrecognized for voltage."""
        channels = [_vchan("VRY", unit="MW", side="primary", primary_ratio=275.0)]
        ev = resolve_voltage_group_evidence(channels)
        winding_cands = [c for c in ev.primary_nominal_candidates if "comtrade" in c.source]
        assert not winding_cands


# ---------------------------------------------------------------------------
# Incomplete phase sets
# ---------------------------------------------------------------------------

class TestIncompletePhaseSet:
    """Single-channel or partial-phase groups still produce evidence."""

    def test_single_phase_primary_ll(self):
        """One channel only: evidence still present, group is incomplete."""
        channels = [_vchan("MCRS VRY", unit="kV", side="primary", primary_ratio=275.0)]
        ev = resolve_voltage_group_evidence(channels)
        # Still has evidence
        assert len(ev.primary_nominal_candidates) >= 1
        assert ev.has_contradictions is False

    def test_two_of_three_phases(self):
        """Two channels, same nominal: consistent, no contradictions."""
        channels = [
            _vchan("MCRS VRY", unit="kV", side="primary", primary_ratio=275.0),
            _vchan("MCRS VYB", unit="kV", side="primary", primary_ratio=275.0),
        ]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.primary_nominal_consistent is True
        assert ev.has_contradictions is False
        assert ev.sufficient_for_auto_nominal is True


# ---------------------------------------------------------------------------
# Candidate determinable but insufficient for automatic authority
# ---------------------------------------------------------------------------

class TestCandidateDeterminableButNotSufficient:
    """Evidence identifies a candidate value but cannot establish auto-authority."""

    def test_low_confidence_only_not_sufficient(self):
        """BEN channel with primary_rating only (no name token, side unknown):
        candidate present (low confidence) but NOT sufficient for auto.
        """
        channels = [_vchan("VA", unit="kV", side="unknown", primary_ratio=76.2)]
        ev = resolve_voltage_group_evidence(channels)
        assert len(ev.primary_nominal_candidates) >= 1  # candidate exists
        assert ev.sufficient_for_auto_nominal is False   # but NOT sufficient

    def test_name_token_no_reference_not_sufficient(self):
        """Name token present (275 kV) but channel reference undetermined.
        Candidate is present; denominator cannot be computed without reference.
        """
        channels = [_vchan("275KV POWER", unit="kV", side="primary")]
        ev = resolve_voltage_group_evidence(channels)
        # 'POWER' has no phase token → channel_reference may be undetermined
        # Nominal candidate from '275KV' token should still be present
        name_cands = [c for c in ev.primary_nominal_candidates if c.source == "name_token"]
        assert name_cands
        # Regardless of reference, check that denominator requires it
        if ev.channel_reference is None:
            assert ev.primary_denominator_determinable is False
            assert ev.sufficient_for_auto_nominal is False

    def test_secondary_side_candidate_not_sufficient_for_nominal(self):
        """Secondary-side measurements provide candidates but require redesign (C1)."""
        channels = [
            _vchan("JMHE VRY", unit="kV", side="secondary", primary_ratio=132.0, secondary_ratio=0.110),
        ]
        ev = resolve_voltage_group_evidence(channels)
        # Candidate may exist (low-confidence primary winding)
        # But sufficient_for_auto_nominal must be False
        assert ev.sufficient_for_auto_nominal is False
        assert REASON_SECONDARY_REQUIRES_REDESIGN in ev.insufficient_reasons

    def test_unknown_side_medium_confidence_sufficient_for_nominal_not_side(self):
        """Name token (medium confidence) with unknown side:
        sufficient_for_auto_nominal = True (we know WHAT the nominal is)
        sufficient_for_auto_side   = False (we don't know WHICH side).
        """
        channels = [_vchan("275KV VRY", unit="kV", side="unknown")]
        ev = resolve_voltage_group_evidence(channels)
        # Medium confidence from name token
        assert any(c.confidence == "medium" for c in ev.primary_nominal_candidates)
        # Nominal auto is achievable (we know it's 275 kV)
        assert ev.sufficient_for_auto_nominal is True
        # Side auto is NOT achievable
        assert ev.sufficient_for_auto_side is False
        assert REASON_SIDE_UNKNOWN in ev.insufficient_reasons


# ---------------------------------------------------------------------------
# Current — CT winding rating vs equipment nominal current
# ---------------------------------------------------------------------------

class TestCurrentGroupEvidence:
    """Current group evidence: CT exclusion, no auto-Ibase."""

    def test_ct_primary_rating_present_and_excluded(self):
        """CT primary winding rating is present in data but excluded (C5, DEC-050 §11)."""
        channels = [
            _ichan("MCRS IA", unit="kA", side="primary", primary_ratio=0.6),  # 600 A CT
            _ichan("MCRS IB", unit="kA", side="primary", primary_ratio=0.6),
            _ichan("MCRS IC", unit="kA", side="primary", primary_ratio=0.6),
        ]
        ev = resolve_current_group_evidence(channels)

        assert ev.ct_primary_excluded is True
        assert len(ev.ct_primary_ratings_ka) == 3
        for ka in ev.ct_primary_ratings_ka:
            assert math.isclose(ka, 0.6, rel_tol=1e-6)
        assert ev.sufficient_for_auto_ibase is False
        assert REASON_CT_PRIMARY_EXCLUDED in ev.insufficient_reasons

    def test_ct_primary_is_not_equipment_nominal_current(self):
        """CT primary winding (0.6 kA) must NOT be treated as Ibase.
        Equipment nominal current for a 100 MVA, 132 kV transformer would be
        Ibase = 100 / (√3 × 132) = 0.4374 kA — a completely different value.
        The resolver must never confuse these.
        """
        channels = [_ichan("IA", unit="kA", side="primary", primary_ratio=0.6)]
        ev = resolve_current_group_evidence(channels)

        # CT primary is captured but excluded
        assert ev.ct_primary_excluded is True
        assert REASON_CT_PRIMARY_EXCLUDED in ev.insufficient_reasons
        # No auto-Ibase regardless of what the CT rating is
        assert ev.sufficient_for_auto_ibase is False
        # The reason must include "no equipment current" — MVA+Vbase still required
        assert REASON_NO_EQUIPMENT_CURRENT in ev.insufficient_reasons

    def test_no_ct_ratio_still_no_auto_ibase(self):
        """Even without CT data, Ibase cannot be auto-determined."""
        channels = [_ichan("IA", unit="kA", side="primary")]
        ev = resolve_current_group_evidence(channels)
        assert ev.sufficient_for_auto_ibase is False
        assert REASON_NO_EQUIPMENT_CURRENT in ev.insufficient_reasons
        assert ev.ct_primary_excluded is False

    def test_equipment_mva_derived_current_requires_manual_input(self):
        """Equipment-rating Ibase = Sbase / (√3 × Vbase_LL).
        In Slice 5A, Sbase is not derivable from channel descriptors.
        The evidence module acknowledges this and reports it as insufficient.
        """
        # Even if the linked voltage group has auto-resolved Vbase,
        # Sbase still requires manual engineer input.
        channels = [_ichan("IA", unit="kA", side="primary", primary_ratio=0.6)]
        ev = resolve_current_group_evidence(channels)
        assert ev.sufficient_for_auto_ibase is False
        # Both CT-exclusion and missing equipment current are reported
        assert REASON_NO_EQUIPMENT_CURRENT in ev.insufficient_reasons

    def test_a_unit_current_channels(self):
        """Current channels with unit='A' (not 'kA'): ratio normalized to kA."""
        channels = [_ichan("IA", unit="A", side="primary", primary_ratio=600.0)]
        ev = resolve_current_group_evidence(channels)
        assert ev.ct_primary_excluded is True
        # 600 A → 0.6 kA
        assert len(ev.ct_primary_ratings_ka) == 1
        assert math.isclose(ev.ct_primary_ratings_ka[0], 0.6, rel_tol=1e-6)

    def test_mixed_sides_current_contradiction(self):
        """Some current channels primary, some secondary: contradiction."""
        channels = [
            _ichan("IA", unit="kA", side="primary", primary_ratio=0.6),
            _ichan("IB", unit="kA", side="secondary", secondary_ratio=0.001),
        ]
        ev = resolve_current_group_evidence(channels)
        assert ev.has_contradictions is True
        assert REASON_MIXED_SIDES in ev.contradiction_reasons
        assert ev.measurement_side == "unknown"

    def test_no_current_channels_in_group(self):
        """Group with no current channels: empty evidence."""
        channels = [_vchan("VRY", unit="kV", side="primary")]
        ev = resolve_current_group_evidence(channels)
        assert REASON_NO_CURRENT_CHANNELS in ev.insufficient_reasons
        assert ev.sufficient_for_auto_ibase is False


# ---------------------------------------------------------------------------
# No voltage channels
# ---------------------------------------------------------------------------

class TestNoVoltageChannels:
    def test_empty_group(self):
        ev = resolve_voltage_group_evidence([])
        assert REASON_NO_VOLTAGE_CHANNELS in ev.insufficient_reasons
        assert ev.sufficient_for_auto_nominal is False

    def test_current_channels_only(self):
        channels = [_ichan("IA", unit="kA", side="primary")]
        ev = resolve_voltage_group_evidence(channels)
        assert REASON_NO_VOLTAGE_CHANNELS in ev.insufficient_reasons


# ---------------------------------------------------------------------------
# Numerical precision
# ---------------------------------------------------------------------------

class TestNumericalPrecision:
    def test_primary_lg_132kv_sqrt3_precision(self):
        """76.2 × √3 = 131.9822715... — consistent with 132 kV within 5% tolerance."""
        channels = [_vchan("VRN", unit="kV", side="primary", primary_ratio=76.2)]
        ev = resolve_voltage_group_evidence(channels)
        winding_cands = [c for c in ev.primary_nominal_candidates if "lg" in c.source]
        assert winding_cands
        expected = 76.2 * SQRT_3
        assert math.isclose(winding_cands[0].value_kv, expected, rel_tol=1e-9)

    def test_secondary_lg_primary_ll_sqrt3_precision(self):
        """Secondary L-G primary_ll_kv_from_ratio uses same √3 constant."""
        channels = [
            _vchan("VA", unit="kV", side="secondary", primary_ratio=76.2, secondary_ratio=0.0635),
        ]
        ev = resolve_voltage_group_evidence(channels)
        assert ev.secondary_measured is not None
        expected = 76.2 * SQRT_3
        assert math.isclose(
            ev.secondary_measured.primary_ll_kv_from_ratio, expected, rel_tol=1e-9
        )

    def test_v_to_kv_conversion_exact(self):
        """275000 V → 275.0 kV exactly within floating-point precision."""
        channels = [_vchan("VRY", unit="V", side="primary", primary_ratio=275_000.0)]
        ev = resolve_voltage_group_evidence(channels)
        winding_cands = [c for c in ev.primary_nominal_candidates if "ll" in c.source]
        assert winding_cands
        assert math.isclose(winding_cands[0].value_kv, 275.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Helper for readability
# ---------------------------------------------------------------------------

def _all_close(values: list[float], expected: float, rel_tol: float = 0.01) -> bool:
    return all(math.isclose(v, expected, rel_tol=rel_tol) for v in values)
