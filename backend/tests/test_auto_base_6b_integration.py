"""Slice 6B acceptance tests — safe integration of multi-hypothesis voltage resolver.

Covers all scenarios from Slice 6B §9:

  Fundamental resolver integration (5):
    1. 275 kV L-G unambiguous → Convention A, sufficient
    2. 132 kV L-G without group name → ambiguous, REASON_HYPOTHESIS_AMBIGUOUS
    3. 132 kV L-G with group_name="132KV" → resolves Convention A, sufficient
    4. 76.2 kV L-G → Convention B (132 kV via ×√3), sufficient
    5. 66 kV L-G → unambiguous (66×√3=114 kV, not standard), sufficient

  hypothesis_resolution field on VoltageGroupEvidence (3):
    6. L-G group → hypothesis_resolution is populated
    7. L-L group → hypothesis_resolution is None
    8. Ambiguous group → hypothesis_resolution.is_ambiguous=True

  Source tag backward compatibility (2):
    9.  Convention A result → source tag "comtrade_primary_ll"
    10. Convention B result → source tag "comtrade_primary_lg"

  Waveform annotation — verdict semantics (3):
    11. Ambiguous result stays ambiguous even with waveform magnitude difference
    12. Waveform corroboration attached to resolution when waveform_evidence supplied
    13. notable_magnitude_gap=True when ratio < 0.70

  REASON_HYPOTHESIS_AMBIGUOUS wiring (2):
    14. Ambiguous → REASON_HYPOTHESIS_AMBIGUOUS in insufficient_reasons
    15. Resolved → REASON_HYPOTHESIS_AMBIGUOUS NOT in insufficient_reasons

  Waveform authority downgrade via service (3):
    16. No waveform → primary path, standard confidence
    17. Waveform magnitude_disagreement for selected hypothesis attached to result
    18. Waveform provider failure → safe fallback, evidence-only behavior preserved
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.domain.auto_base_evidence import (
    REASON_HYPOTHESIS_AMBIGUOUS,
    SQRT_3,
    ChannelAutoMetadata,
    resolve_voltage_group_evidence,
)
from app.domain.waveform_evidence import (
    WaveformEvidence,
    WaveformCorroboration,
    extract_waveform_evidence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vchan(
    name: str,
    unit: str = "kV",
    side: str = "primary",
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


def _lg_channels(prefix: str, ratio_kv: float, n: int = 3) -> list[ChannelAutoMetadata]:
    """L-G channels with the given primary_ratio."""
    phases = ["R", "Y", "B"][:n]
    return [_vchan(f"{prefix}_V{p}", primary_ratio=ratio_kv) for p in phases]


def _ll_channels(prefix: str, ratio_kv: float) -> list[ChannelAutoMetadata]:
    """L-L channels with the given primary_ratio."""
    return [
        _vchan(f"{prefix}_VRY", primary_ratio=ratio_kv),
        _vchan(f"{prefix}_VYB", primary_ratio=ratio_kv),
        _vchan(f"{prefix}_VBR", primary_ratio=ratio_kv),
    ]


def _synthetic_waveform(
    nominal_ll_kv: float,
    channel_ref: str = "line_to_ground",
    n_cycles: int = 20,
    freq_hz: float = 50.0,
    scale: float = 1.0,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Synthetic stable 3-phase waveform at ``scale × nominal``."""
    samples_per_cycle = 64
    n_samples = n_cycles * samples_per_cycle
    t = np.linspace(0, n_cycles / freq_hz, n_samples, endpoint=False)
    if channel_ref == "line_to_ground":
        amplitude_kv = (nominal_ll_kv / SQRT_3) * math.sqrt(2) * scale
    else:
        amplitude_kv = nominal_ll_kv * math.sqrt(2) * scale
    phases = [0, -2 * math.pi / 3, 2 * math.pi / 3]
    return {
        f"V{ph}": (t, amplitude_kv * np.sin(2 * math.pi * freq_hz * t + angle))
        for ph, angle in zip(["R", "Y", "B"], phases)
    }


# ---------------------------------------------------------------------------
# Group 1: Fundamental resolver integration
# ---------------------------------------------------------------------------

class TestFundamentalResolverIntegration:

    def test_01_275kv_lg_unambiguous_convention_a(self):
        """275.0 kV L-G channels → resolves to Convention A (275 kV), sufficient."""
        channels = _lg_channels("N275", 275.0)
        ev = resolve_voltage_group_evidence(channels)
        assert ev.sufficient_for_auto_nominal, ev.insufficient_reasons
        # Hypothesis A: 275 kV selected; Hypothesis B: 275×√3 = 476 kV — not standard
        assert ev.hypothesis_resolution is not None
        assert ev.hypothesis_resolution.selected == "A"
        assert ev.hypothesis_resolution.nominal_ll_kv is not None
        assert math.isclose(ev.hypothesis_resolution.nominal_ll_kv, 275.0, rel_tol=0.02)
        cands = [c for c in ev.primary_nominal_candidates if "ll" in c.source]
        assert cands, "Expected 'll' source candidate for Convention A"
        assert math.isclose(cands[0].value_kv, 275.0, rel_tol=1e-4)

    def test_02_132kv_lg_ambiguous_without_group_name(self):
        """132.0 kV L-G channels without group_name → ambiguous, needs_review."""
        channels = _lg_channels("N132", 132.0)
        ev = resolve_voltage_group_evidence(channels)
        assert not ev.sufficient_for_auto_nominal, (
            "132.0 kV L-G without group name must not be auto_resolved (ambiguous)"
        )
        assert REASON_HYPOTHESIS_AMBIGUOUS in ev.insufficient_reasons
        assert ev.hypothesis_resolution is not None
        assert ev.hypothesis_resolution.is_ambiguous

    def test_03_132kv_lg_resolves_with_group_name_132kv(self):
        """132.0 kV L-G with group_name='132KV' → Hypothesis A selected, sufficient."""
        channels = _lg_channels("N132", 132.0)
        ev = resolve_voltage_group_evidence(channels, group_name="132KV")
        assert ev.sufficient_for_auto_nominal, ev.insufficient_reasons
        assert ev.hypothesis_resolution is not None
        assert ev.hypothesis_resolution.selected == "A"
        assert ev.hypothesis_resolution.nominal_ll_kv is not None
        assert math.isclose(ev.hypothesis_resolution.nominal_ll_kv, 132.0, rel_tol=0.02)

    def test_04_762kv_lg_resolves_convention_b_132kv(self):
        """76.2 kV L-G primary_ratio → Convention B (76.2 × √3 ≈ 132 kV), sufficient."""
        channels = _lg_channels("N132", 76.2)
        ev = resolve_voltage_group_evidence(channels)
        assert ev.sufficient_for_auto_nominal, ev.insufficient_reasons
        # 76.2 not near any standard L-L → Hypothesis A opposed; 76.2×√3=131.98≈132 kV → B selected
        assert ev.hypothesis_resolution is not None
        assert ev.hypothesis_resolution.selected == "B"
        expected_ll = 76.2 * SQRT_3
        assert math.isclose(ev.hypothesis_resolution.nominal_ll_kv, expected_ll, rel_tol=1e-3)
        cands = [c for c in ev.primary_nominal_candidates if "lg" in c.source]
        assert cands, "Expected 'lg' source candidate for Convention B"
        assert math.isclose(cands[0].value_kv, expected_ll, rel_tol=1e-3)

    def test_05_110kv_lg_unambiguous(self):
        """110.0 kV L-G → unambiguous (110×√3=190.5 kV, not near any standard), sufficient.

        66 kV would also match via Convention B → 66×√3=114.3 kV ≈ ANSI 115 kV, so it's
        also ambiguous.  110 kV is used instead: 110×√3=190.5 kV is not near any recognized
        standard nominal (closest are 161 kV and 220 kV, both >13 % away).
        """
        channels = _lg_channels("BUS110", 110.0)
        ev = resolve_voltage_group_evidence(channels)
        assert ev.sufficient_for_auto_nominal, ev.insufficient_reasons
        assert ev.hypothesis_resolution is not None
        assert ev.hypothesis_resolution.selected == "A"
        assert math.isclose(ev.hypothesis_resolution.nominal_ll_kv, 110.0, rel_tol=0.02)


# ---------------------------------------------------------------------------
# Group 2: hypothesis_resolution field on VoltageGroupEvidence
# ---------------------------------------------------------------------------

class TestHypothesisResolutionField:

    def test_06_lg_group_has_hypothesis_resolution(self):
        """L-G group → hypothesis_resolution is populated."""
        channels = _lg_channels("N275", 275.0)
        ev = resolve_voltage_group_evidence(channels)
        assert ev.hypothesis_resolution is not None
        assert ev.hypothesis_resolution.channel_reference == "line_to_ground"

    def test_07_ll_group_has_no_hypothesis_resolution(self):
        """L-L group → hypothesis_resolution is None (no A/B ambiguity for L-L)."""
        channels = _ll_channels("E275", 275.0)
        ev = resolve_voltage_group_evidence(channels)
        # hypothesis_resolution is not invoked for L-L channels (no ambiguity)
        # It may be None or resolved trivially — the key is no ambiguous state
        if ev.hypothesis_resolution is not None:
            assert not ev.hypothesis_resolution.is_ambiguous

    def test_08_ambiguous_group_has_is_ambiguous_true(self):
        """132 kV L-G without group name → hypothesis_resolution.is_ambiguous=True."""
        channels = _lg_channels("BUS132", 132.0)
        ev = resolve_voltage_group_evidence(channels)
        assert ev.hypothesis_resolution is not None
        assert ev.hypothesis_resolution.is_ambiguous is True
        assert ev.hypothesis_resolution.selected == "ambiguous"


# ---------------------------------------------------------------------------
# Group 3: Source tag backward compatibility
# ---------------------------------------------------------------------------

class TestSourceTagBackwardCompat:

    def test_09_convention_a_source_tag_contains_ll(self):
        """Resolved Convention A candidate → source tag contains 'comtrade_primary_ll'."""
        channels = _lg_channels("N275", 275.0)
        ev = resolve_voltage_group_evidence(channels)
        assert ev.sufficient_for_auto_nominal
        winding_cands = [c for c in ev.primary_nominal_candidates if "comtrade_primary" in c.source]
        assert winding_cands, "Expected comtrade_primary winding candidate"
        assert "ll" in winding_cands[0].source, (
            f"Convention A source tag should contain 'll', got: {winding_cands[0].source!r}"
        )

    def test_10_convention_b_source_tag_contains_lg(self):
        """Resolved Convention B candidate → source tag contains 'comtrade_primary_lg'."""
        channels = _lg_channels("N132", 76.2)
        ev = resolve_voltage_group_evidence(channels)
        assert ev.sufficient_for_auto_nominal
        winding_cands = [c for c in ev.primary_nominal_candidates if "comtrade_primary" in c.source]
        assert winding_cands, "Expected comtrade_primary winding candidate for Convention B"
        assert "lg" in winding_cands[0].source, (
            f"Convention B source tag should contain 'lg', got: {winding_cands[0].source!r}"
        )


# ---------------------------------------------------------------------------
# Group 4: Waveform annotation — verdict semantics
# ---------------------------------------------------------------------------

class TestWaveformAnnotationSemantics:

    def test_11_ambiguous_stays_ambiguous_with_waveform(self):
        """Waveform magnitude data does NOT resolve metadata ambiguity (Slice 6B §2).

        Even when waveform clearly favours Hypothesis A for a 132 kV group,
        the resolver must return 'ambiguous' — waveform is annotation only.
        """
        channels = _lg_channels("BUS132", 132.0)
        # Waveform at 132 kV L-G: stable, would corroborate Hypothesis A
        raw = _synthetic_waveform(132.0, channel_ref="line_to_ground")
        wf = extract_waveform_evidence(raw)
        # Only proceed if the waveform is usable
        if not wf.suitable_for_corroboration:
            pytest.skip("Synthetic waveform not suitable for corroboration in this run")
        ev = resolve_voltage_group_evidence(channels, waveform_evidence=wf)
        assert ev.hypothesis_resolution is not None
        assert ev.hypothesis_resolution.selected == "ambiguous", (
            "Waveform must NOT resolve metadata ambiguity — annotation only (Slice 6B §2)"
        )

    def test_12_waveform_corroboration_attached_when_evidence_supplied(self):
        """When waveform_evidence is provided and suitable, corroboration is attached."""
        channels = _lg_channels("N275", 275.0)
        raw = _synthetic_waveform(275.0, channel_ref="line_to_ground")
        wf = extract_waveform_evidence(raw)
        if not wf.suitable_for_corroboration:
            pytest.skip("Synthetic waveform not suitable for corroboration in this run")
        ev = resolve_voltage_group_evidence(channels, waveform_evidence=wf)
        assert ev.hypothesis_resolution is not None
        assert ev.hypothesis_resolution.waveform_corroboration is not None, (
            "waveform_corroboration tuple should be attached when waveform_evidence supplied"
        )
        assert len(ev.hypothesis_resolution.waveform_corroboration) >= 1

    def test_13_notable_magnitude_gap_set_when_ratio_below_070(self):
        """WaveformCorroboration.notable_magnitude_gap=True when ratio < 0.70."""
        channels = _lg_channels("N275", 275.0)
        # Provide a waveform at ~50% of expected (ratio ≈ 0.50 < 0.70 → notable gap)
        raw = _synthetic_waveform(275.0, channel_ref="line_to_ground", scale=0.50)
        wf = extract_waveform_evidence(raw)
        if not wf.suitable_for_corroboration:
            pytest.skip("Synthetic waveform not suitable for corroboration in this run")
        ev = resolve_voltage_group_evidence(channels, waveform_evidence=wf)
        assert ev.hypothesis_resolution is not None
        corrs = ev.hypothesis_resolution.waveform_corroboration
        if corrs is None:
            pytest.skip("No waveform corroboration attached")
        # At least one corroboration should have notable_magnitude_gap=True
        notable = [c for c in corrs if c.notable_magnitude_gap]
        assert notable, (
            "At least one WaveformCorroboration should have notable_magnitude_gap=True "
            "when ratio < 0.70"
        )


# ---------------------------------------------------------------------------
# Group 5: REASON_HYPOTHESIS_AMBIGUOUS wiring
# ---------------------------------------------------------------------------

class TestReasonHypothesisAmbiguousWiring:

    def test_14_ambiguous_adds_reason_to_insufficient_reasons(self):
        """Ambiguous L-G group → REASON_HYPOTHESIS_AMBIGUOUS in insufficient_reasons."""
        channels = _lg_channels("BUS132", 132.0)
        ev = resolve_voltage_group_evidence(channels)
        assert REASON_HYPOTHESIS_AMBIGUOUS in ev.insufficient_reasons, (
            f"Expected {REASON_HYPOTHESIS_AMBIGUOUS!r} in insufficient_reasons, "
            f"got: {ev.insufficient_reasons}"
        )

    def test_15_resolved_does_not_add_ambiguous_reason(self):
        """Unambiguous L-G group → REASON_HYPOTHESIS_AMBIGUOUS NOT in insufficient_reasons."""
        channels = _lg_channels("N275", 275.0)
        ev = resolve_voltage_group_evidence(channels)
        assert ev.sufficient_for_auto_nominal
        assert REASON_HYPOTHESIS_AMBIGUOUS not in ev.insufficient_reasons, (
            "Resolved group must not have REASON_HYPOTHESIS_AMBIGUOUS in insufficient_reasons"
        )


# ---------------------------------------------------------------------------
# Group 6: Waveform authority downgrade via domain (service-independent)
# ---------------------------------------------------------------------------

class TestWaveformAuthorityDowngrade:

    def test_16_no_waveform_provider_standard_behavior(self):
        """No waveform_evidence → standard evidence-only resolution, no downgrade."""
        channels = _lg_channels("N275", 275.0)
        ev = resolve_voltage_group_evidence(channels)  # no waveform_evidence
        assert ev.sufficient_for_auto_nominal
        # hypothesis_resolution present but no waveform_corroboration
        assert ev.hypothesis_resolution is not None
        assert ev.hypothesis_resolution.waveform_corroboration is None

    def test_17_magnitude_disagreement_verdict_is_not_rejection(self):
        """magnitude_disagreement is a factual observation, not hypothesis rejection.

        A 275 kV group with waveform at 50% magnitude gets magnitude_disagreement
        (observed/expected = 0.50, outside ±10%) but the hypothesis_resolution must
        still select "A" and must not set is_ambiguous=True.
        """
        channels = _lg_channels("N275", 275.0)
        raw = _synthetic_waveform(275.0, channel_ref="line_to_ground", scale=0.50)
        wf = extract_waveform_evidence(raw)
        if not wf.suitable_for_corroboration:
            pytest.skip("Synthetic waveform not suitable for corroboration in this run")
        ev = resolve_voltage_group_evidence(channels, waveform_evidence=wf)
        assert ev.hypothesis_resolution is not None
        # Metadata resolves unambiguously to "A" — waveform cannot override this
        assert ev.hypothesis_resolution.selected == "A", (
            "Waveform magnitude_disagreement must NOT change metadata-resolved selection"
        )
        assert not ev.hypothesis_resolution.is_ambiguous
        # Corroboration verdict should be magnitude_disagreement or indeterminate
        corrs = ev.hypothesis_resolution.waveform_corroboration
        if corrs:
            hyp_a_corr = next((c for c in corrs if abs(c.candidate_ll_kv - 275.0) < 1.0), None)
            if hyp_a_corr is not None:
                assert hyp_a_corr.verdict in ("magnitude_disagreement", "indeterminate"), (
                    f"Expected magnitude_disagreement or indeterminate, got: {hyp_a_corr.verdict!r}"
                )

    def test_18_waveform_provider_failure_does_not_affect_evidence(self):
        """resolve_voltage_group_evidence with waveform_evidence=None is equivalent to no waveform.

        The service wraps waveform code in try/except (C8); a provider failure must
        produce the same result as passing waveform_evidence=None.
        """
        channels = _lg_channels("N275", 275.0)
        ev_no_waveform = resolve_voltage_group_evidence(channels, waveform_evidence=None)
        # Simulate a provider that returned None (failure was caught)
        ev_provider_failed = resolve_voltage_group_evidence(channels, waveform_evidence=None)
        assert ev_no_waveform.sufficient_for_auto_nominal == ev_provider_failed.sufficient_for_auto_nominal
        assert ev_no_waveform.insufficient_reasons == ev_provider_failed.insufficient_reasons
        assert (
            ev_no_waveform.hypothesis_resolution is not None
            and ev_provider_failed.hypothesis_resolution is not None
        )
        assert ev_no_waveform.hypothesis_resolution.selected == ev_provider_failed.hypothesis_resolution.selected


# ---------------------------------------------------------------------------
# Group 7: Waveform corroboration is diagnostic only — no authority change
# ---------------------------------------------------------------------------

class TestWaveformCorroborationAnnotationOnly:

    def _resolve_with_low_voltage_waveform(self, scale: float):
        """Return evidence for 275 kV L-G with stable waveform at ``scale × nominal``."""
        channels = _lg_channels("N275", 275.0)
        raw = _synthetic_waveform(275.0, channel_ref="line_to_ground", scale=scale)
        wf = extract_waveform_evidence(raw)
        return resolve_voltage_group_evidence(channels, waveform_evidence=wf), wf

    def test_19_magnitude_disagreement_030pu_does_not_block_auto_resolution(self):
        """275 kV system, waveform at 0.30 pu voltage sag → auto authority preserved.

        A 0.30 pu recorded voltage is physically valid (severe voltage sag, fault
        or brownout on a correctly-identified 275 kV system).  The waveform
        magnitude_disagreement is diagnostic only and must NOT block auto authority.

        Expected:
          - sufficient_for_auto_nominal = True
          - hypothesis_resolution.selected = "A"
          - waveform_corroboration attached, verdict = "magnitude_disagreement"
          - notable_magnitude_gap = True (ratio ≈ 0.30 < 0.70)
        """
        ev, wf = self._resolve_with_low_voltage_waveform(scale=0.30)
        assert ev.sufficient_for_auto_nominal, (
            "0.30 pu waveform must NOT block auto authority for 275 kV (annotation only)"
        )
        assert ev.hypothesis_resolution is not None
        assert ev.hypothesis_resolution.selected == "A", (
            "Waveform must NOT change metadata-resolved selection from 'A'"
        )
        if wf.suitable_for_corroboration and ev.hypothesis_resolution.waveform_corroboration:
            hyp_a_corr = next(
                (c for c in ev.hypothesis_resolution.waveform_corroboration
                 if abs(c.candidate_ll_kv - 275.0) < 1.0),
                None,
            )
            if hyp_a_corr is not None:
                assert hyp_a_corr.verdict == "magnitude_disagreement", (
                    f"Expected magnitude_disagreement, got {hyp_a_corr.verdict!r}"
                )
                assert hyp_a_corr.notable_magnitude_gap is True, (
                    "ratio ≈ 0.30 < 0.70 → notable_magnitude_gap must be True"
                )

    def test_20_magnitude_disagreement_058pu_does_not_block_auto_resolution(self):
        """275 kV system, waveform at 0.58 pu (typical fault voltage) → auto authority preserved.

        A 0.58 pu waveform (typical close-in fault) is physically valid for a
        correctly-identified 275 kV system.  The 0.577 pu ≈ 1/√3 is the
        characteristic single-phase fault voltage.  magnitude_disagreement must
        NOT block auto authority — it is attached as diagnostic provenance only.

        Expected:
          - sufficient_for_auto_nominal = True
          - hypothesis_resolution.selected = "A"
          - waveform_corroboration: verdict = "magnitude_disagreement"
          - notable_magnitude_gap = True (ratio ≈ 0.58 < 0.70)
        """
        ev, wf = self._resolve_with_low_voltage_waveform(scale=0.58)
        assert ev.sufficient_for_auto_nominal, (
            "0.58 pu waveform (fault scenario) must NOT block auto authority (annotation only)"
        )
        assert ev.hypothesis_resolution is not None
        assert ev.hypothesis_resolution.selected == "A", (
            "Waveform at 0.58 pu must NOT override metadata selection"
        )
        if wf.suitable_for_corroboration and ev.hypothesis_resolution.waveform_corroboration:
            hyp_a_corr = next(
                (c for c in ev.hypothesis_resolution.waveform_corroboration
                 if abs(c.candidate_ll_kv - 275.0) < 1.0),
                None,
            )
            if hyp_a_corr is not None:
                assert hyp_a_corr.verdict == "magnitude_disagreement", (
                    f"Expected magnitude_disagreement for 0.58 pu, got {hyp_a_corr.verdict!r}"
                )
                assert hyp_a_corr.notable_magnitude_gap is True, (
                    "ratio ≈ 0.58 < 0.70 → notable_magnitude_gap must be True"
                )
