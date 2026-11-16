"""Multi-hypothesis Voltage reference resolver (PU-001B design prototype).

Evaluates two competing hypotheses for a Line-to-Ground COMTRADE channel whose
``primary_ratio`` field may encode one of two things:

  Hypothesis A — ``primary_ratio`` IS the nominal system L-L voltage directly.
                 (Most common in IEC/EN protection relay COMTRADE files.)

  Hypothesis B — ``primary_ratio`` is the VT phase-winding (L-G) primary rating;
                 the nominal system L-L voltage is ``primary_ratio × √3``.

Each hypothesis is evaluated independently against multiple evidence dimensions.
When only one hypothesis is supported, it is selected. When both are plausible,
or when neither is supported, the resolver returns an explicit ambiguous / none
state rather than selecting arbitrarily.

For Line-to-Line channels there is no ambiguity: ``primary_ratio`` is already
in the channel's own L-L geometry, so it is used directly.

This module is a **prototype for the PU-001B design review**. It is NOT yet
wired into the import lifecycle or ``auto_base_service``. The live resolver
remains ``auto_base_evidence.resolve_voltage_group_evidence()``.

Design constraints (inherited from auto_base_evidence):
  C2  VT winding ratings are transformation metadata, not authoritative
      nominal-system values. They produce candidates; they do not establish
      ground truth.
  C3  Voltage reference geometry (L-L / L-G) is determined from channel names.
  C4  Channel name kV tokens do not establish measurement side.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from app.domain.auto_base_evidence import (
    SQRT_3,
    _STANDARD_NOMINAL_KV,
    _STANDARD_NOMINAL_KV_TOL,
    _is_near_standard_nominal_kv,
    _to_kv,
    ChannelAutoMetadata,
)
from app.domain.voltage_reference import (
    LINE_TO_GROUND,
    LINE_TO_LINE,
    detect_voltage_reference,
)

if TYPE_CHECKING:
    from app.domain.waveform_evidence import WaveformCorroboration, WaveformEvidence

# ---------------------------------------------------------------------------
# Public type aliases
# ---------------------------------------------------------------------------

HypothesisID = Literal["A", "B", "ambiguous", "none"]
EvidenceResult = Literal["support", "oppose", "neutral", "absent"]

# ---------------------------------------------------------------------------
# Tolerance constants
# ---------------------------------------------------------------------------

# Standard nominal match tolerance — 2 % relative (inherited from auto_base_evidence)
_SNM_TOL = _STANDARD_NOMINAL_KV_TOL

# Tight tolerance for name-token corroboration (1 % relative)
_NT_TOL = 0.01

# Typical VT secondary circuit voltages (L-L at relay terminal), V
# Used for winding-ratio plausibility check
_TYPICAL_VT_SECONDARY_V = (63.5, 110.0, 115.0, 120.0)
_VT_SECONDARY_TOL = 0.10  # 10 % tolerance

# Channel name kV token: matches "275KV", "132kV", "275 KV", etc.
_NAME_KV_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*KV\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Evidence dimension
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EvidenceDimension:
    """One piece of evidence contributing to hypothesis evaluation."""
    name: str           # machine-readable label
    result: EvidenceResult
    weight: float       # positive = support; zero = neutral/absent
    details: str        # human-readable explanation


# ---------------------------------------------------------------------------
# Per-hypothesis summary
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class HypothesisSummary:
    """Evaluation result for one hypothesis."""
    id: HypothesisID                                # "A" or "B"
    candidate_ll_kv: float                          # Proposed nominal L-L kV
    score: float                                    # Sum of supporting evidence weights
    evidence: tuple[EvidenceDimension, ...]
    is_supported: bool                              # At least one positive-weight dimension
    is_opposed: bool                                # At least one opposition dimension
    support_reasons: tuple[str, ...]
    opposition_reasons: tuple[str, ...]


# ---------------------------------------------------------------------------
# Resolution result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class VoltageHypothesisResolution:
    """Full multi-hypothesis resolution for one voltage measurement group."""

    # Input summary
    channel_names: tuple[str, ...]
    channel_reference: str | None   # LINE_TO_LINE / LINE_TO_GROUND / None

    # Hypothesis results (None when not applicable, e.g. L-L channels)
    hypothesis_a: HypothesisSummary | None
    hypothesis_b: HypothesisSummary | None

    # Selection
    selected: HypothesisID          # "A" / "B" / "ambiguous" / "none"
    nominal_ll_kv: float | None     # Resolved nominal; None when ambiguous or none
    denominator_kv: float | None    # Applicable PU denominator for the recorded waveform

    # Confidence and provenance
    confidence: Literal["high", "medium", "low"] | None
    provenance: str                 # Human-readable resolution path
    insufficient_reasons: tuple[str, ...]

    # Is this result suitable for automatic configuration?
    is_resolved: bool               # True when selected is "A" or "B"
    is_ambiguous: bool              # True when both hypotheses remain plausible
    suitable_for_auto: bool         # Resolved AND high/medium confidence AND not opposed

    # Waveform corroboration (populated when waveform_evidence is supplied)
    waveform_corroboration: tuple[WaveformCorroboration, ...] | None = None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def evaluate_voltage_hypotheses(
    channels: list[ChannelAutoMetadata],
    *,
    group_name: str | None = None,
    waveform_evidence: WaveformEvidence | None = None,
) -> VoltageHypothesisResolution:
    """Evaluate Hypothesis A and B for a candidate voltage measurement group.

    Args:
        channels: Channel metadata for the group (same format as
            ``resolve_voltage_group_evidence``).
        group_name: Optional group or source name, searched for kV tokens.
        waveform_evidence: Optional waveform evidence from the same group.
            When provided and ``suitable_for_corroboration`` is True, the
            corroboration result is attached and may resolve an ambiguity.

    Returns:
        ``VoltageHypothesisResolution`` with full provenance.
    """
    # Avoid import at module level to prevent circular imports
    from app.domain.waveform_evidence import (
        WaveformEvidence as _WE,
        corroborate_hypothesis as _corr,
    )

    voltage_chs = [c for c in channels if (c.engineering_type or "").lower() == "voltage"]
    if not voltage_chs:
        return _no_voltage_channels(channels)

    names = tuple(c.name for c in voltage_chs)
    channel_reference, ref_note = _detect_ref(names)

    if channel_reference == LINE_TO_LINE:
        resolution = _resolve_ll(voltage_chs, channel_reference, group_name)
    elif channel_reference == LINE_TO_GROUND:
        resolution = _resolve_lg(voltage_chs, channel_reference, group_name)
    else:
        resolution = _reference_undetermined(voltage_chs, channel_reference, ref_note or "")

    # --- Apply waveform corroboration (Slice 6A) ---
    if waveform_evidence is None or not waveform_evidence.suitable_for_corroboration:
        return resolution

    # Build corroboration for each active hypothesis
    corr_list: list[WaveformCorroboration] = []
    hyps_to_corroborate: list[HypothesisSummary] = []
    if resolution.hypothesis_a is not None:
        hyps_to_corroborate.append(resolution.hypothesis_a)
    if resolution.hypothesis_b is not None:
        hyps_to_corroborate.append(resolution.hypothesis_b)

    # For already-resolved L-L (no A/B), still attach a corroboration
    if not hyps_to_corroborate and resolution.nominal_ll_kv is not None:
        corr = _corr(resolution.nominal_ll_kv, channel_reference, waveform_evidence)
        corr_list.append(corr)
        return _replace_waveform_corr(resolution, tuple(corr_list))

    if not hyps_to_corroborate:
        return resolution

    for hyp in hyps_to_corroborate:
        corr = _corr(hyp.candidate_ll_kv, channel_reference, waveform_evidence)
        corr_list.append(corr)

    # Waveform corroboration is an annotation only.  It does NOT change the
    # selected hypothesis — competing hypotheses must be excluded by independent
    # metadata evidence (DEC-212 / Slice 6B §2).  An ambiguous metadata result
    # remains ambiguous even when waveform magnitude favours one candidate.
    return _replace_waveform_corr(resolution, tuple(corr_list))


# ---------------------------------------------------------------------------
# Line-to-Line path — no hypothesis ambiguity
# ---------------------------------------------------------------------------

def _resolve_ll(
    chs: list[ChannelAutoMetadata],
    channel_reference: str,
    group_name: str | None,
) -> VoltageHypothesisResolution:
    """L-L channels: primary_ratio is already the L-L voltage. No A/B ambiguity."""
    names = tuple(c.name for c in chs)
    kv_values = []
    for ch in chs:
        kv = _to_kv(ch.primary_ratio, ch.unit)
        if kv is not None and kv >= 2.0:
            kv_values.append(kv)

    if not kv_values:
        return _build_none(names, channel_reference, ("no_valid_primary_ratio_ll",),
                           "L-L channels: no valid primary_ratio in recognized units.")

    nominal = _most_common_kv(kv_values)
    provenance = f"L-L channel geometry: primary_ratio = {nominal:.4g} kV (direct, no disambiguation needed)"
    conf = _snm_confidence(nominal)
    denom = nominal  # L-L denominator = nominal L-L
    return VoltageHypothesisResolution(
        channel_names=names,
        channel_reference=channel_reference,
        hypothesis_a=None,
        hypothesis_b=None,
        selected="A",
        nominal_ll_kv=nominal,
        denominator_kv=denom,
        confidence=conf,
        provenance=provenance,
        insufficient_reasons=(),
        is_resolved=True,
        is_ambiguous=False,
        suitable_for_auto=(conf in ("high", "medium")),
    )


# ---------------------------------------------------------------------------
# Line-to-Ground path — full hypothesis evaluation
# ---------------------------------------------------------------------------

def _resolve_lg(
    chs: list[ChannelAutoMetadata],
    channel_reference: str,
    group_name: str | None,
) -> VoltageHypothesisResolution:
    """L-G channels: evaluate Hypothesis A and B for each channel, then aggregate."""
    names = tuple(c.name for c in chs)
    kv_values = []
    for ch in chs:
        kv = _to_kv(ch.primary_ratio, ch.unit)
        if kv is not None and kv >= 1.0:
            kv_values.append(kv)

    if not kv_values:
        return _build_none(names, channel_reference, ("no_valid_primary_ratio_lg",),
                           "L-G channels: no valid primary_ratio in recognized units.")

    r = _most_common_kv(kv_values)  # Representative primary_ratio for the group

    # Build evidence for each hypothesis using the representative value
    evidence_a = _evaluate_lg_hypothesis("A", r, r, names, group_name, chs)
    evidence_b = _evaluate_lg_hypothesis("B", r, r * SQRT_3, names, group_name, chs)

    # --- Verdict ---
    if evidence_a.is_supported and not evidence_b.is_supported:
        # Only A supported
        nominal = r
        denom = nominal / SQRT_3  # L-G denominator for a nominal L-L system voltage
        conf = _hypothesis_confidence(evidence_a)
        provenance = (
            f"L-G channels: Hypothesis A selected (primary_ratio = {r:.4g} kV is nominal L-L). "
            f"Support: {'; '.join(evidence_a.support_reasons)}. "
            f"Hypothesis B not supported ({r * SQRT_3:.4g} kV ≠ any standard nominal)."
        )
        return _build_resolved(names, channel_reference, evidence_a, evidence_b,
                                "A", nominal, denom, conf, provenance)

    elif evidence_b.is_supported and not evidence_a.is_supported:
        # Only B supported
        nominal = r * SQRT_3
        denom = r  # Phase-winding primary voltage = L-G denominator on a √3-system
        conf = _hypothesis_confidence(evidence_b)
        provenance = (
            f"L-G channels: Hypothesis B selected (primary_ratio {r:.4g} kV × √3 = "
            f"{nominal:.4g} kV is nominal L-L). "
            f"Support: {'; '.join(evidence_b.support_reasons)}. "
            f"Hypothesis A not supported ({r:.4g} kV ≠ any standard nominal)."
        )
        return _build_resolved(names, channel_reference, evidence_a, evidence_b,
                                "B", nominal, denom, conf, provenance)

    elif evidence_a.is_supported and evidence_b.is_supported:
        # Both match a standard nominal — check whether opposition breaks the tie.
        # If one hypothesis is explicitly opposed (e.g. a name token points elsewhere)
        # while the other is not, the unOpposed hypothesis is selected.
        a_opposed = evidence_a.is_opposed
        b_opposed = evidence_b.is_opposed

        if b_opposed and not a_opposed:
            # Hypothesis B is opposed; Hypothesis A is unOpposed → select A
            nominal = r
            denom = nominal / SQRT_3
            conf = _hypothesis_confidence(evidence_a)
            provenance = (
                f"L-G channels: Hypothesis A selected (both A and B initially plausible, "
                f"but B is opposed by: {'; '.join(evidence_b.opposition_reasons)}). "
                f"A support: {'; '.join(evidence_a.support_reasons)}."
            )
            return _build_resolved(names, channel_reference, evidence_a, evidence_b,
                                    "A", nominal, denom, conf, provenance)

        elif a_opposed and not b_opposed:
            # Hypothesis A is opposed; Hypothesis B is unOpposed → select B
            nominal = r * SQRT_3
            denom = r
            conf = _hypothesis_confidence(evidence_b)
            provenance = (
                f"L-G channels: Hypothesis B selected (both A and B initially plausible, "
                f"but A is opposed by: {'; '.join(evidence_a.opposition_reasons)}). "
                f"B support: {'; '.join(evidence_b.support_reasons)}."
            )
            return _build_resolved(names, channel_reference, evidence_a, evidence_b,
                                    "B", nominal, denom, conf, provenance)

        else:
            # Neither has discriminating opposition — genuinely ambiguous
            provenance = (
                f"L-G channels: AMBIGUOUS — both Hypothesis A ({r:.4g} kV) and "
                f"Hypothesis B ({r * SQRT_3:.4g} kV) match a recognized standard nominal. "
                f"Cannot determine convention without additional context (name token, "
                f"VT ratio, or waveform corroboration)."
            )
            return VoltageHypothesisResolution(
                channel_names=names,
                channel_reference=channel_reference,
                hypothesis_a=evidence_a,
                hypothesis_b=evidence_b,
                selected="ambiguous",
                nominal_ll_kv=None,
                denominator_kv=None,
                confidence=None,
                provenance=provenance,
                insufficient_reasons=("both_hypotheses_plausible",),
                is_resolved=False,
                is_ambiguous=True,
                suitable_for_auto=False,
            )

    else:
        # Neither matches any standard — insufficient evidence
        provenance = (
            f"L-G channels: neither {r:.4g} kV (Hypothesis A) nor "
            f"{r * SQRT_3:.4g} kV (Hypothesis B) match any recognized standard "
            f"nominal voltage. Cannot determine convention automatically."
        )
        return _build_none(names, channel_reference,
                           ("no_standard_nominal_match",), provenance,
                           hypothesis_a=evidence_a, hypothesis_b=evidence_b)


# ---------------------------------------------------------------------------
# Evidence evaluation
# ---------------------------------------------------------------------------

def _evaluate_lg_hypothesis(
    hyp_id: HypothesisID,
    raw_ratio: float,
    candidate_ll: float,
    channel_names: tuple[str, ...],
    group_name: str | None,
    chs: list[ChannelAutoMetadata],
) -> HypothesisSummary:
    """Score one hypothesis against all evidence dimensions."""
    dims: list[EvidenceDimension] = []

    # --- Dimension 1: Standard nominal match (SNM) ---
    snm_match, snm_ref, snm_tol = _snm_match_detail(candidate_ll)
    if snm_match:
        pct_off = abs(candidate_ll - snm_ref) / snm_ref * 100
        dims.append(EvidenceDimension(
            name="standard_nominal_match",
            result="support",
            weight=2.0 if pct_off < 1.0 else 1.0,
            details=f"{candidate_ll:.4g} kV within {pct_off:.2f}% of standard {snm_ref:.4g} kV",
        ))
    else:
        dims.append(EvidenceDimension(
            name="standard_nominal_match",
            result="absent",
            weight=0.0,
            details=f"{candidate_ll:.4g} kV not near any recognized standard nominal voltage",
        ))

    # --- Dimension 2: Channel name kV token corroboration (NT) ---
    nt_weight = 0.0
    nt_result: EvidenceResult = "absent"
    nt_detail = "No kV token found in channel names"
    for name in channel_names:
        m = _NAME_KV_RE.search(name)
        if m:
            tok_kv = float(m.group(1))
            if tok_kv > 0 and abs(tok_kv - candidate_ll) / max(tok_kv, 1.0) <= _NT_TOL:
                nt_result = "support"
                nt_weight = 3.0
                nt_detail = f"Channel name '{name}' contains '{tok_kv} KV' matching candidate {candidate_ll:.4g} kV"
                break
            elif tok_kv > 0 and abs(tok_kv - candidate_ll) / max(tok_kv, 1.0) > 0.10:
                # Explicit token clearly opposing this candidate
                nt_result = "oppose"
                nt_weight = -2.0
                nt_detail = (f"Channel name '{name}' contains '{tok_kv} KV' — "
                             f"does not match candidate {candidate_ll:.4g} kV")
    dims.append(EvidenceDimension(
        name="name_token_corroboration",
        result=nt_result,
        weight=nt_weight,
        details=nt_detail,
    ))

    # --- Dimension 3: Group name kV token (GNT) ---
    gnt_weight = 0.0
    gnt_result: EvidenceResult = "absent"
    gnt_detail = "No group name provided"
    if group_name:
        m = _NAME_KV_RE.search(group_name)
        if m:
            tok_kv = float(m.group(1))
            if tok_kv > 0 and abs(tok_kv - candidate_ll) / max(tok_kv, 1.0) <= _NT_TOL:
                gnt_result = "support"
                gnt_weight = 2.0
                gnt_detail = (f"Group name '{group_name}' contains '{tok_kv} KV' "
                              f"matching candidate {candidate_ll:.4g} kV")
            elif tok_kv > 0 and abs(tok_kv - candidate_ll) / max(tok_kv, 1.0) > 0.10:
                gnt_result = "oppose"
                gnt_weight = -1.5
                gnt_detail = (f"Group name '{group_name}' contains '{tok_kv} KV' — "
                              f"does not match candidate {candidate_ll:.4g} kV")
            else:
                gnt_detail = f"Group name token {tok_kv} KV — inconclusive for candidate {candidate_ll:.4g} kV"
        else:
            gnt_detail = f"No kV token found in group name '{group_name}'"
    dims.append(EvidenceDimension(
        name="group_name_token",
        result=gnt_result,
        weight=gnt_weight,
        details=gnt_detail,
    ))

    # --- Dimension 4: VT winding ratio plausibility (WRP) ---
    # Only applicable when secondary_ratio is available.
    # For Hypothesis A: primary winding = candidate_ll (L-L) → phase winding = candidate_ll/√3
    # For Hypothesis B: primary winding = raw_ratio (phase-winding = candidate_ll/√3)
    # In both cases the phase-winding primary voltage (kV) divided by secondary_ratio (kV)
    # should give a winding ratio consistent with typical VT designs.
    wrp_weight = 0.0
    wrp_result: EvidenceResult = "absent"
    wrp_detail = "No secondary_ratio available for winding-ratio plausibility check"
    secs = [c.secondary_ratio for c in chs if c.secondary_ratio is not None and c.secondary_ratio > 0]
    if secs:
        sec_kv = _to_kv(secs[0], chs[0].unit)
        if sec_kv is not None and sec_kv > 0:
            # Secondary terminal voltage in V
            sec_v = sec_kv * 1000.0
            if hyp_id == "A":
                # Hypothesis A: phase-winding primary = candidate_ll/√3 (kV)
                primary_phase_kv = candidate_ll / SQRT_3
            else:
                # Hypothesis B: phase-winding primary = raw_ratio
                primary_phase_kv = raw_ratio
            # VT winding ratio = primary_phase / secondary (both in same units)
            vt_ratio = (primary_phase_kv * 1000.0) / sec_v
            # Is secondary close to a typical VT secondary voltage?
            sec_typical = any(
                abs(sec_v - tv) / max(tv, 1.0) <= _VT_SECONDARY_TOL
                for tv in _TYPICAL_VT_SECONDARY_V
            )
            if sec_typical and 100 < vt_ratio < 5000:
                # A plausible VT ratio is a necessary but not sufficient
                # condition. When both Convention A and B produce ratios in
                # the typical range (e.g. secondary=110 V → A=1443:1,
                # B=2500:1) this dimension cannot discriminate between them.
                # Granting "support" weight to both would make them equally
                # "supported" and force an ambiguous verdict even though the
                # SNM dimension already unambiguously selects one candidate.
                # Plausibility is therefore "neutral" (no score contribution);
                # only an implausible ratio actively opposes a hypothesis.
                wrp_result = "neutral"
                wrp_weight = 0.0
                wrp_detail = (f"VT winding ratio {vt_ratio:.0f}:1 "
                              f"(primary phase {primary_phase_kv:.4g} kV / "
                              f"secondary {sec_v:.1f} V) plausible — "
                              f"neutral: does not discriminate between hypotheses")
            elif sec_v > 500:
                wrp_result = "oppose"
                wrp_weight = -0.5
                wrp_detail = (f"Secondary terminal voltage {sec_v:.1f} V is not typical "
                              f"for a protection VT ({_TYPICAL_VT_SECONDARY_V})")
            else:
                wrp_detail = (f"VT winding ratio {vt_ratio:.0f}:1 from secondary "
                              f"{sec_v:.1f} V — plausibility inconclusive")
    dims.append(EvidenceDimension(
        name="vt_winding_ratio_plausibility",
        result=wrp_result,
        weight=wrp_weight,
        details=wrp_detail,
    ))

    # --- Score and verdict ---
    score = sum(d.weight for d in dims if d.weight > 0)
    is_supported = score > 0
    is_opposed = any(d.weight < 0 for d in dims)
    support_reasons = tuple(d.details for d in dims if d.weight > 0)
    opposition_reasons = tuple(d.details for d in dims if d.weight < 0)

    return HypothesisSummary(
        id=hyp_id,
        candidate_ll_kv=candidate_ll,
        score=score,
        evidence=tuple(dims),
        is_supported=is_supported,
        is_opposed=is_opposed,
        support_reasons=support_reasons,
        opposition_reasons=opposition_reasons,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _replace_waveform_corr(
    res: VoltageHypothesisResolution,
    corr: tuple[WaveformCorroboration, ...],
) -> VoltageHypothesisResolution:
    """Return a new VoltageHypothesisResolution with waveform_corroboration set."""
    return VoltageHypothesisResolution(
        channel_names=res.channel_names,
        channel_reference=res.channel_reference,
        hypothesis_a=res.hypothesis_a,
        hypothesis_b=res.hypothesis_b,
        selected=res.selected,
        nominal_ll_kv=res.nominal_ll_kv,
        denominator_kv=res.denominator_kv,
        confidence=res.confidence,
        provenance=res.provenance,
        insufficient_reasons=res.insufficient_reasons,
        is_resolved=res.is_resolved,
        is_ambiguous=res.is_ambiguous,
        suitable_for_auto=res.suitable_for_auto,
        waveform_corroboration=corr,
    )


def _detect_ref(names: tuple[str, ...]) -> tuple[str | None, str | None]:
    """Wrapper for detect_voltage_reference returning (reference, note)."""
    det = detect_voltage_reference(list(names))
    ref = getattr(det, "reference", None)
    if ref == LINE_TO_LINE:
        return LINE_TO_LINE, None
    if ref == LINE_TO_GROUND:
        return LINE_TO_GROUND, None
    reason = getattr(det, "reason", None) or "undetermined"
    return None, str(reason)


def _most_common_kv(kv_values: list[float]) -> float:
    """Return the median kV value from a list of channel primary_ratios."""
    return sorted(kv_values)[len(kv_values) // 2]


def _snm_match_detail(kv: float) -> tuple[bool, float, float]:
    """Return (matched, closest_standard_kv, tolerance_used) for SNM check."""
    best_ref = 0.0
    best_diff = float("inf")
    for std in _STANDARD_NOMINAL_KV:
        diff = abs(kv - std) / std
        if diff < best_diff:
            best_diff = diff
            best_ref = std
    matched = best_diff <= _SNM_TOL
    return matched, best_ref, _SNM_TOL


def _snm_confidence(kv: float) -> Literal["high", "medium", "low"] | None:
    """Confidence based solely on how well kv matches a standard nominal."""
    matched, best_ref, _ = _snm_match_detail(kv)
    if not matched:
        return None
    pct = abs(kv - best_ref) / best_ref
    if pct < 0.005:
        return "high"
    return "medium"


def _hypothesis_confidence(h: HypothesisSummary) -> Literal["high", "medium", "low"]:
    """Derive confidence from a hypothesis summary."""
    snm = next((d for d in h.evidence if d.name == "standard_nominal_match"), None)
    nt = next((d for d in h.evidence if d.name in ("name_token_corroboration", "group_name_token")
               and d.weight > 0), None)
    snm_weight = snm.weight if snm else 0.0
    if nt is not None and snm_weight > 0:
        return "high"
    if snm_weight >= 2.0:
        return "high"
    if snm_weight >= 1.0:
        return "medium"
    return "low"


def _build_resolved(
    names: tuple[str, ...],
    channel_reference: str,
    ha: HypothesisSummary,
    hb: HypothesisSummary,
    selected: HypothesisID,
    nominal: float,
    denom: float,
    conf: Literal["high", "medium", "low"],
    provenance: str,
) -> VoltageHypothesisResolution:
    return VoltageHypothesisResolution(
        channel_names=names,
        channel_reference=channel_reference,
        hypothesis_a=ha,
        hypothesis_b=hb,
        selected=selected,
        nominal_ll_kv=nominal,
        denominator_kv=denom,
        confidence=conf,
        provenance=provenance,
        insufficient_reasons=(),
        is_resolved=True,
        is_ambiguous=False,
        suitable_for_auto=(conf in ("high", "medium") and not ha.is_opposed and not hb.is_opposed),
    )


def _build_none(
    names: tuple[str, ...],
    channel_reference: str | None,
    reasons: tuple[str, ...],
    provenance: str,
    *,
    hypothesis_a: HypothesisSummary | None = None,
    hypothesis_b: HypothesisSummary | None = None,
) -> VoltageHypothesisResolution:
    return VoltageHypothesisResolution(
        channel_names=names,
        channel_reference=channel_reference,
        hypothesis_a=hypothesis_a,
        hypothesis_b=hypothesis_b,
        selected="none",
        nominal_ll_kv=None,
        denominator_kv=None,
        confidence=None,
        provenance=provenance,
        insufficient_reasons=reasons,
        is_resolved=False,
        is_ambiguous=False,
        suitable_for_auto=False,
    )


def _no_voltage_channels(channels: list[ChannelAutoMetadata]) -> VoltageHypothesisResolution:
    names = tuple(c.name for c in channels)
    return _build_none(names, None, ("no_voltage_channels",),
                       "No voltage channels in group.")


def _reference_undetermined(
    chs: list[ChannelAutoMetadata],
    reference: str | None,
    note: str,
) -> VoltageHypothesisResolution:
    names = tuple(c.name for c in chs)
    return _build_none(names, reference,
                       ("voltage_reference_undetermined",),
                       f"Channel reference geometry could not be determined: {note}")
